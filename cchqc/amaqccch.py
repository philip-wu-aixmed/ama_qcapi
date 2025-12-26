""" Docstring for CCHQC.v1.qcapi.cchqc.amaqccch
  endpoints for providing analyzed metadata for specified slide
"""
from loguru import logger
from fastapi import APIRouter, Request, HTTPException
from cchqc.config import serviceHistory, TSaction
from cchqc.qcxfuncs import get_st_mtime
from cchqc.qcxfuncs import query_all_slide_name, query_qcresult_for_slide
from cchqc.qcxfuncs import change_qc_score_criteria, change_qc_magic_number, get_current_magic_number

qcapicch = APIRouter()

# ---------------------------------------------------------
#  endpoints for CCH QC workflow
# ---------------------------------------------------------

@qcapicch.get('/allslides', summary='query all the analyzed slide image files')
async def get_all_slides(slide_type: str, request: Request):
    """
    query all the analyzed slide image files in image storage
      :param slide_type: urine or thyroid
    """
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'there is no slide for {slide_type} slides'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},allslides,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'there is no slide for {slide_type} slides')
    logger.info(f'get_all_slides({slide_type})')
    err = query_all_slide_name(slide_type)
    if err['code'] < 0:
        logger.error(err['data'])
        serviceHistory.append(f"{procts.action_at()},allslides,{request.client.host},failed,{procts.consumed_time()},err['data']")
        raise HTTPException(status_code=404, detail=err['data'])
    errmsg = f"found {len(err['data'])} slide image files"
    serviceHistory.append(f"{procts.action_at()},allslides,{request.client.host},completed,{procts.consumed_time()},{errmsg}")
    return err['data']

@qcapicch.get('/v0/slide', summary='query analyzed metadata for QC, return 2 signals')
async def get_v0_slide_qc_result(slide_type: str, slide_id: str, request: Request):
    """
    endpoint.v0 for querying analyzed metadata of specified slide
      :param slide_type: urine or thyroid
      :param slide_id: slide id for querying
    """
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'{slide_type} {slide_id} can not be found'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'{slide_type} {slide_id} can not be found')
    logger.info(f'starting get_slide_qc_result({slide_type}, {slide_id}) ...')
    ## find slide_id with pathology_id
    err = query_all_slide_name(slide_type)
    if err['code'] < 0:
        errmsg = 'lost the connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
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
    qcresult = {}
    if slide_found:
        err = query_qcresult_for_slide(slide_type, slidename, 1)
        qcresult = err['data']
    else:
        err = {'code': -3, 'data': None}
    if err['code'] == -1:
        errmsg = 'lost net connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
    elif err['code'] == -2:
        errmsg = f'can not find any metadata for {slide_type} slide {slide_id}'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
    elif err['code'] == -3:
        errmsg = f'{slide_type} slide {slide_id} does not exist'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
    if err['code'] < 0:
        raise HTTPException(status_code=404, detail=errmsg)

    serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},completed,{procts.consumed_time()},{qcresult['rawdata']}")
    return {
        'signal1': qcresult['signal'][0],
        'signal2': qcresult['signal'][1],
        'medpath': qcresult['medpath'],
        'asposix': qcresult['posixpath'],
        'medfile': qcresult['medname'],
        'rawdata': qcresult['rawdata'],
        'refnote': qcresult['refnote']
    }

@qcapicch.get('/v1/slide', summary='query analyzed metadata for QC, return 4 signals')
async def get_v1_slide_qc_result(slide_type: str, slide_id: str, request: Request):
    """
    endpoint.v1 for querying analyzed metadata of specified slide
      :param slide_type: urine or thyroid
      :param slide_id: slide id for querying
    """
    procts = TSaction()
    if slide_type.lower() not in ['urine', 'thyroid']:
        errmsg = f'{slide_type} {slide_id} can not be found'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=f'{slide_type} {slide_id} can not be found')
    logger.info(f'starting get_slide_qc_result({slide_type}, {slide_id}) ...')
    ## find slide_id with pathology_id
    err = query_all_slide_name(slide_type)
    if err['code'] < 0:
        errmsg = 'lost the connection to image storage'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
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
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
    elif err['code'] == -2:
        errmsg = f'can not find any metadata for {slide_type} slide {slide_id}'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
    if err['code'] < 0:
        raise HTTPException(status_code=404, detail=errmsg)

    serviceHistory.append(f"{procts.action_at()},slide,{request.client.host},completed,{procts.consumed_time()},{qcresult['rawdata']}")
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

@qcapicch.post('/setScoreThreshold', summary='set urine score threshold', include_in_schema=True)
async def set_score_threshold_for_qc(s: float, request: Request):
    """
    endpoint for change urine score criteria, default is 0.4
      :param s: score threshold for criteria
    """
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
    serviceHistory.append(f"{procts.action_at()},setScoreCriteria,{request.client.host},{errstat},{procts.consumed_time()},{retmsg}")
    return {
        'score threshold': ret[2]
    }

@qcapicch.get('/currentQCmagic', summary='get urine QC magic nnumber', include_in_schema=True)
async def get_magic_number_for_qc(request: Request):
    """
    endpoint for querying urine QC MAGIC number
    """
    procts = TSaction()
    ret = get_current_magic_number()
    serviceHistory.append(f"{procts.action_at()},currentQCmagic,{request.client.host},completed,{procts.consumed_time()},{ret}")
    return {
        'suspicious': ret[0],
        'atypical': ret[1]
    }

@qcapicch.post('/changeQCmagic', summary='change urine QC magic number', include_in_schema=True)
async def change_magic_number_for_qc(s: int, a: int, request: Request):
    """
    endpoint for changing urine QC magic number
      :param s: magic number for suspicious cell
      :param a: magic number for atypical cell
    """
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
    serviceHistory.append(f"{procts.action_at()},changeQCmagic,{request.client.host},{errstat},{procts.consumed_time()},{retstr}")
    return retstr
