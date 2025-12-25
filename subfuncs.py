from fastapi import APIRouter, Query, Request, HTTPException
from typing import List, Optional
from loguru import logger
import os
from config import MYENV, serviceHistory, TSaction
from qcxfuncs import openMEDwithCytoInsights, summarizeCellCounts

localapi = APIRouter()

##---------------------------------------------------------
## local private endpoint: open .med with cytoinsights
##---------------------------------------------------------
@localapi.get('/openmed', summary='open .med with CytoInsights', include_in_schema=True)
async def open_medfile(medfile: str, request: Request):
    procts = TSaction()
    if os.path.exists(medfile) == False:
        errmsg = f'{medfile} does not exist'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},openmed,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    elif os.path.splitext(medfile)[1] not in ['.med', '.aix']:
        errmsg = f'{medfile} can not be recognized by viewer application'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},openmed,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    err = openMEDwithCytoInsights(medfile)
    errstat = 'completed' if err['code'] == 0 else 'failed'
    serviceHistory.append(f"{procts.action_at()},openmed,{request.client.host},{errstat},{procts.consumed_time()},{err['data']}")
    return err

##---------------------------------------------------------
## local private endpoint: summarize analyzed metadata to CSV
##---------------------------------------------------------
@localapi.get('/summarize', summary='summarize cells count to CSV', include_in_schema=True)
async def summarize_cells_count(
    category: str,
    request: Request,
    aixpath: Optional[str] = Query(None, description='specified folder for summarizing')
):
    procts = TSaction()
    if aixpath and os.path.isdir(aixpath) == False:
        errmsg = f"{aixpath} is not a folder"
        serviceHistory.append(f"{procts.action_at()},summarize,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    csvfname = ''
    workpath = aixpath if aixpath else ''
    if category.lower() in ['urine', 'thyroid']:
        csvfname = summarizeCellCounts(category, workpath)
    if not csvfname:
        errmsg = f'can not find any .aix file in {aixpath}'
        serviceHistory.append(f"{procts.action_at()},summary,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    serviceHistory.append(f"{procts.action_at()},summary,{request.client.host},completed,{procts.consumed_time()},{csvfname}")
    return f'{csvfname} completed!'

