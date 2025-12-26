""" CCHQC.v1.qcapi.cchqc.dummycch
simulate CCH API for requesting access token and querying slide information
"""
import os
import csv
from datetime import datetime, timedelta
from loguru import logger
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
from cchqc.config import MYENV

router_cchapi = APIRouter()
router_cchimg = APIRouter()

security = HTTPBearer()

class RequestBody(BaseModel):
    """data for requesting access token"""
    funccode: str
    iss: str

class TokenResponse(BaseModel):
    """response data for access token"""
    access_token: str
    token_type: str = 'bearer'
    expires_at: str

def create_access_token(data: dict):
    """
    create access token with email account
    args:
      data (dict): RequestBody for creating access token
    """
    to_encode = data.copy()
    expiretime = datetime.now()+timedelta(days=MYENV.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expiretime})
    try:
        encoded_jwt = jwt.encode(to_encode, MYENV.SECRET_KEY, algorithm=MYENV.ALGORITHM)
        return encoded_jwt, expiretime.isoformat()
    except jwt.ExpiredSignatureError:
        errmsg = 'Token expired'
    except jwt.InvalidTokenError:
        errmsg = 'Invalid token'
    raise HTTPException(status_code=401, detail=errmsg)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    verify access token with Bearer
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, MYENV.SECRET_KEY, algorithms=[MYENV.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        errmsg = 'Token expired'
    except jwt.InvalidTokenError:
        errmsg = 'Invalid token'
    raise HTTPException(status_code=401, detail=errmsg)

def acquire_cch_slide_profile(slideid):
    """
    simulate CCH API for acquiring slide profile
      :param slideid (str): slide id
    """
    dummycsv = os.path.join(os.getenv('LOCALAPPDATA'), 'ama_qcapi', MYENV.DUMMY_SLIDE)

    with open(dummycsv, 'r', encoding='utf-8') as sinfo:
        dict_reader = csv.DictReader(sinfo)
        slideprofile = list(dict_reader)
    ## finde slide id
    filtered = filter(lambda x: x['npath_no'] == slideid, slideprofile)
    found_slide = list(filtered)
    if len(found_slide) > 0:    ## found more than 1 slide
        if len(found_slide) > 1:
            logger.warning(f'more than 1 slide ID is {slideid}')
        return found_slide[0]
    else:   ## can't find profile for {slideid}
        found_slide = {'npath_no': slideid, 'login_tim': '', 'orgsou': ''}
        return found_slide


def append_cch_slide_profile(cchslide):
    """
    dummy function to append one slide profile to dummy CSV
      :param cchslide (dict): slide profile
    """
    dummycsv = os.path.join(os.getenv('LOCALAPPDATA'), 'ama_qcapi', MYENV.DUMMY_SLIDE)
    try:
        with open(dummycsv, mode='a', newline="", encoding='utf-8') as sinfo:
            dict_append = sinfo.writer()
            dict_append.writerow(cchslide)
    except csv.Error as e:
        logger.error(f"CSV Error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise

@router_cchapi.post("/encode", summary='get access token with request token', include_in_schema=True)
async def request_access_token(
    request_token: str = Query(..., description='request token for authentication'),
    credentials: RequestBody = ...
):
    """
    dummy API for simulating CCH API: request_access_token
      :param request_token: request token for specified user identity
      :param credentials: user identity
    """
    if request_token != MYENV.REQUEST_KEY:
        raise HTTPException(status_code=401, detail=f"Invalid request token: {request_token}")
    # check funccode/iss
    if credentials.funccode != MYENV.DUMMY_ADMIN or credentials.iss != MYENV.DUMMY_EMAIL:
        raise HTTPException(status_code=401, detail=f"Invalid identity: {credentials}")

    token, expires = create_access_token(data={'sub': credentials.funccode, "who": credentials.iss})
    #return TokenResponse(access_token=token, expires_at=expires)
    logger.trace(f'{token} will expire at {expires}')
    return token

@router_cchapi.post("/verify", summary='verify access token', include_in_schema=True)
async def verify_access_token(token: str):
    """
    verify access token
      :param token: access token to verify
    """
    try:
        payload = jwt.decode(token, MYENV.SECRET_KEY, algorithms=[MYENV.ALGORITHM])
        #logger.debug(f"token verify: {payload.get('sub')}: {payload.get('exp')}")
        tsexp = payload.get('exp')
        owner = payload.get('who')
        dtnow = datetime.now()
        dtexp = datetime.fromtimestamp(tsexp)
        if dtnow < dtexp:
            is_valid = 'true'
        else:
            is_valid = 'false'
            logger.error(f"({owner}) access token expired ({dtexp.isoformat()})")
        #return {'valid': True, 'message': note}
        return is_valid
    except jwt.exceptions.InvalidTokenError as e:
        errmsg = f'Invalid or expired token: {e}'
    raise HTTPException(status_code=401, detail=errmsg)

@router_cchimg.get("/QryPaHisInfo/{SlideNo}", summary='dummy API to get slide information', include_in_schema=True)
async def get_slide_information(SlideNo: str):
    """
    simulate CCH API for acquiring slide profile with access token
      :param SlideNo: slide id for querying slide information
    """
    found_slide = acquire_cch_slide_profile(SlideNo)
    return found_slide
