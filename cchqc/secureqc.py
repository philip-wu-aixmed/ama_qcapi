""" Docstring for CCHQC.v1.qcapi.cchqc.secureqc
   Secure QCAPI
"""
from datetime import datetime, timedelta
from loguru import logger
import jwt
from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
#from jose import JWTError, jwt
from cchqc.config import MYENV, serviceHistory, TSaction
from cchqc.qcxfuncs import get_st_mtime
from cchqc.qcxfuncs import query_all_slide_name, query_qcresult_for_slide
from cchqc.qcxfuncs import change_qc_score_criteria, change_qc_magic_number, get_current_magic_number

secure_qcapicch = APIRouter()
security = HTTPBearer()

class TokenResponse(BaseModel):
    """ response body for requesting access token """
    access_token: str
    token_type: str = 'bearer'
    expires_at: str

def create_access_token(data: dict):
    """
    create_access_token
      :param data: data for creating access token
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
    """ verify access token """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, MYENV.SECRET_KEY, algorithms=[MYENV.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        errmsg = 'Token expired'
    except jwt.InvalidTokenError:
        errmsg = 'Invalid token'
    raise HTTPException(status_code=401, detail=errmsg)

@secure_qcapicch.post("/getatoken", summary='get access token with email address', include_in_schema=True)
async def request_access_token_forqc(
    request: Request,
    requestor: str = Query(..., description='company email account for authentication')
):
    """
    fastapi.security for QCAPI
      :param requestor: data of requestor identity
    """
    procts = TSaction()
    if '@' not in requestor:
        serviceHistory.append(f"{procts.action_at()},getatoken,{request.client.host},failed,{procts.consumed_time()}, invalid requestor")
        raise HTTPException(status_code=401, detail=f"Invalid email address: {requestor}")
    splitidx = requestor.index('@')
    work = requestor[splitidx+1:]
    name = requestor[:splitidx]
    if work not in MYENV.ACCESS_AVAILABLE_DOMAIN:
        serviceHistory.append(f"{procts.action_at()},getatoken,{request.client.host},failed,{procts.consumed_time()}, f'invalid requestor {requestor}'")
        raise HTTPException(status_code=401, detail=f"Invalid requestor: {requestor}")

    token, expires = create_access_token(data={'sub': work, "who": name})
    serviceHistory.append(f"{procts.action_at()},getatoken,{request.client.host},completed,{procts.consumed_time()}, f'expires at {expires}'")
    return TokenResponse(access_token=token, expires_at=expires)

@secure_qcapicch.post("verifytoken", summary='verify access token', include_in_schema=True)
async def verify_access_token(token: str, request: Request):
    """ verify access token """
    procts = TSaction()
    try:
        payload = jwt.decode(token, MYENV.SECRET_KEY, algorithms=[MYENV.ALGORITHM])
        #note = f"{payload.get('sub')}: {payload.get('exp')}"
        logger.debug(f"verify token: {payload}")
        dtnow = datetime.now()
        dtexp = datetime.fromtimestamp(payload.get('exp'))
        if dtnow < dtexp:
            still_valid = True
        else:
            still_valid = False
            logger.error(f"({payload.get('who')})access token is expired ({payload.get('exp')})")
        serviceHistory.append(f"{procts.action_at()},verifytoken,{request.client.host},completed,{procts.consumed_time()}, f'token is {still_valid}'")
        #return {'valid': True, 'message': note}
        return still_valid
    except jwt.exceptions.InvalidTokenError:
        serviceHistory.append(f"{procts.action_at()},verifytoken,{request.client.host},completed,{procts.consumed_time()}, invalid token")
        errmsg = "Invalid or expired token"
    raise HTTPException(status_code=401, detail=errmsg)

@secure_qcapicch.get('/allslides', summary='query all the analyzed slide image files')
async def get_all_slides(slide_type: str, user_role: str=Depends(verify_token)):
    """ endpoints for CCH QC workflow with access token """
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'there is no slide for {slide_type} slides'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},allslides,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'there is no slide for {slide_type} slides')
    logger.info(f'get_all_slides({slide_type})')
    err = query_all_slide_name(slide_type)
    if err['code'] < 0:
        logger.error(err['data'])
        serviceHistory.append(f"{procts.action_at()},allslides,{user_role['who']},failed,{procts.consumed_time()},err['data']")
        raise HTTPException(status_code=404, detail=err['data'])
    errmsg = f"found {len(err['data'])} slide image files"
    serviceHistory.append(f"{procts.action_at()},allslides,{user_role['who']},completed,{procts.consumed_time()},{errmsg}")
    return err['data']

@secure_qcapicch.get('/v0/slide', summary='query analyzed metadata for QC, return 2 signals')
async def get_v0_slide_qc_result(slide_type: str, slide_id: str, user_role: str=Depends(verify_token)):
    """ v0 endpoint for querying analyzed metadata of specified slide """
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'{slide_type} {slide_id} can not be found'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'{slide_type} {slide_id} can not be found')
    logger.info(f'starting get_slide_qc_result({slide_type}, {slide_id}) ...')
    ## find slide_id with pathology_id
    err = query_all_slide_name(slide_type)
    if err['code'] < 0:
        errmsg = 'lost the connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    slideimages = []
    for slidename in err['data']:
        thisslide = {}
        if slide_id in slidename:
            thisslide['slideid'] = slidename
            thisslide['stmtime'] = get_st_mtime(slide_type, f'{slidename}.med')
            #logger.debug(f'{slidename}: {thisslide['stmtime']}')
            slideimages.append(thisslide)
    slide_found = True
    if len(slideimages) > 1:
        foundslide = sorted(slideimages, key=lambda x: (x['stmtime']), reverse=True)
        #logger.debug(f'foundslide: {foundslide}')
        slidename = foundslide[0]['slideid']
    elif len(slideimages) == 1:
        slidename = slideimages[0]['slideid']
    else:
        slide_found = False
    ##
    logger.debug(f'slideimages: {slideimages}')
    if slide_found:
        err = query_qcresult_for_slide(slide_type, slidename, 1)
        qcresult = err['data']
    else:
        qcresult = {}
        err = {'code': -3, 'data': None}
    if err['code'] == -1:
        errmsg = 'lost net connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
    elif err['code'] == -2:
        errmsg = f'can not find any metadata for {slide_type} slide {slide_id}'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
    elif err['code'] == -3:
        errmsg = f'{slide_type} slide {slide_id} does not exist'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
    if err['code'] < 0:
        raise HTTPException(status_code=404, detail=errmsg)

    serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},completed,{procts.consumed_time()},{qcresult['rawdata']}")
    return {
        'signal1': qcresult['signal'][0],
        'signal2': qcresult['signal'][1],
        'medpath': qcresult['medpath'],
        'asposix': qcresult['posixpath'],
        'medfile': qcresult['medname'],
        'rawdata': qcresult['rawdata'],
        'refnote': qcresult['refnote']
    }

@secure_qcapicch.get('/v1/slide', summary='query analyzed metadata for QC, return 4 signals')
async def get_v1_slide_qc_result(slide_type: str, slide_id: str, user_role: str=Depends(verify_token)):
    """ v1 endpoint for querying analyzed metadata of specified slide """
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'{slide_type} {slide_id} can not be found'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'{slide_type} {slide_id} can not be found')
    logger.info(f'starting get_slide_qc_result({slide_type}, {slide_id}) ...')
    ## find slide_id with pathology_id
    err = query_all_slide_name(slide_type)
    if err['code'] < 0:
        errmsg = 'lost the connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    slideimages = []
    for slidename in err['data']:
        thisslide = {}
        if slide_id in slidename:
            thisslide['slideid'] = slidename
            thisslide['stmtime'] = get_st_mtime(slide_type, f'{slidename}.med')
            #logger.debug(f'{slidename}: {thisslide['stmtime']}')
            slideimages.append(thisslide)
    slide_found = True
    if len(slideimages) > 1:
        foundslide = sorted(slideimages, key=lambda x: (x['stmtime']), reverse=True)
        #logger.debug(f'foundslide: {foundslide}')
        slidename = foundslide[0]['slideid']
    elif len(slideimages) == 1:
        slidename = slideimages[0]['slideid']
    else:
        slide_found = False
    ##
    logger.debug(f'slideimages: {slideimages}')
    if slide_found:
        err = query_qcresult_for_slide(slide_type, slidename, 1)
        qcresult = err['data']
    else:
        qcresult = {}
    if err['code'] == -1:
        errmsg = 'lost net connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
    elif err['code'] == -2:
        errmsg = f'can not find any metadata for {slide_type} slide {slide_id}'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
    if err['code'] < 0:
        raise HTTPException(status_code=404, detail=errmsg)

    serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},completed,{procts.consumed_time()},{qcresult['rawdata']}")
    return {
        'signal1': qcresult['signal'][0],
        'signal2': qcresult['signal'][1],
        'signal3': qcresult['signal'][2],
        'signal4': qcresult['signal'][3],
        'medpath': qcresult['medpath'],
        'asposix': qcresult['posixpath'],
        'medfile': qcresult['medname'],
        'rawdata': qcresult['rawdata'],
        'refnote': qcresult['refnote']
    }

@secure_qcapicch.post('/setScoreThreshold', summary='set urine score threshold', include_in_schema=True)
async def set_score_threshold_for_qc(s: float, user_role: str=Depends(verify_token)):
    """ endpoint for change urine score criteria, default is 0.4 """
    procts = TSaction()
    if s < 0.0 or s > 1.0:
        retmsg = f'invalid threshold {s}, retain current score'
        logger.warning(retmsg)
        errstat = 'failed'
    else:
        change_qc_score_criteria(s)
        retmsg = f'score threshold was set to {s}'
        errstat = 'completed'
    ret = get_current_magic_number()
    serviceHistory.append(f"{procts.action_at()},setScoreCriteria,{user_role['who']},{errstat},{procts.consumed_time()},{retmsg}")
    return {
        'score threshold': ret[2]
    }

@secure_qcapicch.get('/currentQCmagic', summary='get urine QC magic nnumber', include_in_schema=True)
async def get_magic_number_for_qc(user_role: str=Depends(verify_token)):
    """ endpoint for querying urine QC MAGIC number """
    procts = TSaction()
    ret = get_current_magic_number()
    serviceHistory.append(f"{procts.action_at()},currentQCmagic,{user_role['who']},completed,{procts.consumed_time()},{ret}")
    return {
        'suspicious': ret[0],
        'atypical': ret[1]
    }

@secure_qcapicch.post('/changeQCmagic', summary='change urine QC magic number', include_in_schema=True)
async def change_magic_number_for_qc(s: int, a: int, user_role: str=Depends(verify_token)):
    """ endpoint for changing urine QC MAGIC number """
    procts = TSaction()
    ret = change_qc_magic_number(s, a)
    if ret:
        retstr = f'magic number was changed to suspicious:{s}, atypical:{a}'
        logger.info(retstr)
        errstat = 'completed'
    else:
        retstr = 'failed to change magic number'
        logger.warning(retstr)
        errstat = 'failed'
    serviceHistory.append(f"{procts.action_at()},changeQCmagic,{user_role['who']},{errstat},{procts.consumed_time()},{retstr}")
    return retstr
