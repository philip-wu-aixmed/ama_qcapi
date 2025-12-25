from fastapi import APIRouter, Depends, Query, Request, HTTPException
## 
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import JWTError, jwt
##
from datetime import datetime, timedelta
from loguru import logger
from config import MYENV, serviceHistory, TSaction
from qcxfuncs import get_st_mtime
from qcxfuncs import queryAllSlideName, queryQCresult4slide
from qcxfuncs import changeScoreCriteria4QC, changeMagicNumber4QC, getCurrentMagicNumber

secure_qcapicch = APIRouter()
security = HTTPBearer()

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_at: str

##---------------------------------------------------------
## create access token
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
## fastapi.security for QCxAPI
##---------------------------------------------------------
@secure_qcapicch.post("/getatoken", summary='get access token with email address', include_in_schema=True)
async def requestAccessToken4QC(
    request: Request,
    requestor: str = Query(..., description='company email account for authentication')
):
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

##---------------------------------------------------------
## verify access token
##---------------------------------------------------------
@secure_qcapicch.post("verifytoken", summary='verify access token', include_in_schema=True)
async def verifyAccessToken(token: str, request: Request):
    procts = TSaction()
    try:
        payload = jwt.decode(token, MYENV.SECRET_KEY, algorithms=[MYENV.ALGORITHM])
        #note = f"{payload.get('sub')}: {payload.get('exp')}"
        logger.debug(f"verify token: {payload}")
        dtnow = datetime.now()
        dtexp = datetime.fromtimestamp(payload.get('exp'))
        if dtnow < dtexp:
            isValid = True
        else:
            isValid = False
            logger.error(f"({payload.get('who')})access token is expired ({payload.get('exp')})")
        serviceHistory.append(f"{procts.action_at()},verifytoken,{request.client.host},completed,{procts.consumed_time()}, f'token is {isValid}'")
        #return {'valid': True, 'message': note}
        return isValid
    except JWTError:
        serviceHistory.append(f"{procts.action_at()},verifytoken,{request.client.host},completed,{procts.consumed_time()}, invalid token")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

##---------------------------------------------------------
## endpoints for CCH QC workflow with access token
##---------------------------------------------------------
@secure_qcapicch.get('/allslides', summary='query all the analyzed slide image files')
async def get_all_slides(slide_type: str, user_role: str=Depends(verify_token)):
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'there is no slide for {slide_type} slides'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},allslides,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'there is no slide for {slide_type} slides')
    logger.info(f'get_all_slides({slide_type})')
    err = queryAllSlideName(slide_type)
    if err['code'] < 0:
        logger.error(err['data'])
        serviceHistory.append(f"{procts.action_at()},allslides,{user_role['who']},failed,{procts.consumed_time()},err['data']")
        raise HTTPException(status_code=404, detail=err['data'])
    errmsg = f"found {len(err['data'])} slide image files"
    serviceHistory.append(f"{procts.action_at()},allslides,{user_role['who']},completed,{procts.consumed_time()},{errmsg}")
    return err['data']

##---------------------------------------------------------
## v0 endpoint for querying analyzed metadata of specified slide
##---------------------------------------------------------
@secure_qcapicch.get('/v0/slide', summary='query analyzed metadata for QC, return 2 signals')
async def get_v0_slide_qc_result(slide_type: str, slide_id: str, user_role: str=Depends(verify_token)):
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'{slide_type} {slide_id} can not be found'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'{slide_type} {slide_id} can not be found')
    logger.info(f'starting get_slide_qc_result({slide_type}, {slide_id}) ...')
    ## find slide_id with pathology_id
    err = queryAllSlideName(slide_type)
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
        err = queryQCresult4slide(slide_type, slidename, 1)
        qcresult = err['data']
    else:
        err = {'code': -3, 'data': None}
    if err['code'] == -1:
        errmsg = 'lost net connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'lost net connection to image storage')
    elif err['code'] == -2:
        errmsg = f'can not find any metadata for {slide_type} slide {slide_id}'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'can not find any metadata for {slide_type} slide {slide_id}')
    elif err['code'] == -3:
        errmsg = f'{slide_type} slide {slide_id} does not exist'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'can not find any metadata for {slide_type} slide {slide_id}')

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

##---------------------------------------------------------
## v1 endpoint for querying analyzed metadata of specified slide
##---------------------------------------------------------
@secure_qcapicch.get('/v1/slide', summary='query analyzed metadata for QC, return 4 signals')
async def get_v1_slide_qc_result(slide_type: str, slide_id: str, user_role: str=Depends(verify_token)):
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'{slide_type} {slide_id} can not be found'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'{slide_type} {slide_id} can not be found')
    logger.info(f'starting get_slide_qc_result({slide_type}, {slide_id}) ...')
    ## find slide_id with pathology_id
    err = queryAllSlideName(slide_type)
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
        err = queryQCresult4slide(slide_type, slidename, 1)
        qcresult = err['data']
    else:
        qcresult = {}
    if err['code'] == -1:
        errmsg = 'lost net connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'lost net connection to image storage')
    elif err['code'] == -2:
        errmsg = f'can not find any metadata for {slide_type} slide {slide_id}'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{user_role['who']},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'can not find any metadata for {slide_type} slide {slide_id}')

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

##---------------------------------------------------------
## endpoint for change urine score criteria, default is 0.4
##---------------------------------------------------------
@secure_qcapicch.post('/setScoreThreshold', summary='set urine score threshold', include_in_schema=True)
async def set_score_threshold_for_QC(s: float, user_role: str=Depends(verify_token)):
    procts = TSaction()
    if s < 0.0 or s > 1.0:
        retmsg = f'invalid threshold {s}, retain current score'
        logger.warning(retmsg)
        errstat = 'failed'
    else:
        changeScoreCriteria4QC(s)
        retmsg = f'score threshold was set to {s}'
        errstat = 'completed'
    ret = getCurrentMagicNumber()
    serviceHistory.append(f"{procts.action_at()},setScoreCriteria,{user_role['who']},{errstat},{procts.consumed_time()},{retmsg}")
    return {
        'score threshold': ret[2]
    }

##---------------------------------------------------------
## endpoint for change urine QC MAGIC number
##---------------------------------------------------------
@secure_qcapicch.get('/currentQCmagic', summary='get urine QC magic nnumber', include_in_schema=True)
async def get_magic_number_for_QC(user_role: str=Depends(verify_token)):
    procts = TSaction()
    ret = getCurrentMagicNumber()
    serviceHistory.append(f"{procts.action_at()},currentQCmagic,{user_role['who']},completed,{procts.consumed_time()},{ret}")
    return {
        'suspicious': ret[0],
        'atypical': ret[1]
    }

@secure_qcapicch.post('/changeQCmagic', summary='change urine QC magic number', include_in_schema=True)
async def change_magic_number_for_QC(s: int, a: int, user_role: str=Depends(verify_token)):
    procts = TSaction()
    ret = changeMagicNumber4QC(s, a)
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


