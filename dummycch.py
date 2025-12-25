from fastapi import APIRouter, Depends, Query, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
from datetime import datetime, timedelta
from loguru import logger
from config import MYENV
import os, csv

router_cchapi = APIRouter()
router_cchimg = APIRouter()

security = HTTPBearer()

class RequestBody(BaseModel):
    funccode: str
    iss: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_at: str

##---------------------------------------------------------
## create access token with email account
##---------------------------------------------------------
def create_access_token(data: dict):
    to_encode = data.copy()
    expiretime = datetime.now()+timedelta(days=MYENV.ACCESS_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expiretime})
    try:
        encoded_jwt = jwt.encode(to_encode, MYENV.SECRET_KEY, algorithm=MYENV.ALGORITHM)
        return encoded_jwt, expiretime.isoformat()
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')
    
##---------------------------------------------------------
## verify access token
##---------------------------------------------------------
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, MYENV.SECRET_KEY, algorithms=[MYENV.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail='Token expired')
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail='Invalid token')

##---------------------------------------------------------
## simulate CCH API for acquiring slide profile
##---------------------------------------------------------
def acquireCCHslideProfile(slideid):
    dummycsv = os.path.join(os.getenv('LOCALAPPDATA'), 'ama_qcapi', MYENV.DUMMY_SLIDE)

    with open(dummycsv, 'r') as sinfo:
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

##---------------------------------------------------------
## dummy function to append one slide profile to dummy CSV
##---------------------------------------------------------
def appendCCHslideProfile(cchslide):
    dummycsv = os.path.join(os.getenv('LOCALAPPDATA'), 'ama_qcapi', MYENV.DUMMY_SLIDE)
    try:
        with open(dummycsv, mode='a', newline="") as sinfo:
            dict_append = csv.writer()
            dict_append.writerow(cchslide)
    except csv.Error as e:
        logger.error(f"CSV Error: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")

##---------------------------------------------------------
## dummy API for simulating CCH APIs
##---------------------------------------------------------
## dummy API for generate access token
@router_cchapi.post("/encode", summary='get access token with request token', include_in_schema=True)
async def requestAccessToken(
    requestToken: str = Query(..., description='request token for authentication'), 
    credentials: RequestBody = ...
):
    if requestToken != MYENV.REQUEST_KEY:
        raise HTTPException(status_code=401, detail=f"Invalid request token: {requestToken}")
    # check funccode/iss
    if credentials.funccode != MYENV.DUMMY_ADMIN or credentials.iss != MYENV.DUMMY_EMAIL:
        raise HTTPException(status_code=401, detail=f"Invalid identity: {credentials}")

    token, expires = create_access_token(data={'sub': credentials.funccode, "who": credentials.iss})
    #return TokenResponse(access_token=token, expires_at=expires)
    logger.trace(f'{token} will expire at {expires}')
    return token

## verify access token
@router_cchapi.post("/verify", summary='verify access token', include_in_schema=True)
async def verifyAccessToken(token: str):
    try:
        payload = jwt.decode(token, MYENV.SECRET_KEY, algorithms=[MYENV.ALGORITHM])
        #logger.debug(f"token verify: {payload.get('sub')}: {payload.get('exp')}")
        tsexp = payload.get('exp')
        owner = payload.get('who')
        dtnow = datetime.now()
        dtexp = datetime.fromtimestamp(tsexp)
        if dtnow < dtexp:
            isValid = 'true'
        else:
            isValid = 'false'
            logger.error(f"({owner}) access token expired ({dtexp.isoformat()})")
        #return {'valid': True, 'message': note}
        return isValid
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

## simulate CCH API for acquiring slide profile with access token
@router_cchimg.get("/QryPaHisInfo/{SlideNo}", summary='dummy API to get slide information', include_in_schema=True)
async def getSlideInformation(
    SlideNo: str, user_role: str=Depends(verify_token)
):
    found_slide = acquireCCHslideProfile(SlideNo)
    return found_slide
