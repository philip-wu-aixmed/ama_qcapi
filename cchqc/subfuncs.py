""" Docstring for CCHQC.v1.qcapi.cchqc.subfuncs
  private endpoints for testing
"""
import os
from typing import Optional
from loguru import logger
from fastapi import APIRouter, Query, Request, HTTPException
from cchqc.config import serviceHistory, TSaction
from cchqc.qcxfuncs import open_med_with_cytoinsights, summarize_cell_counts_to_csv

localapi = APIRouter()

@localapi.get('/openmed', summary='open .med with CytoInsights', include_in_schema=False)
async def open_medfile(medfile: str, request: Request):
    """ local private endpoint: open .med with cytoinsights """
    procts = TSaction()
    if not os.path.exists(medfile):
        errmsg = f'{medfile} does not exist'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},openmed,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    elif os.path.splitext(medfile)[1] not in ['.med', '.aix']:
        errmsg = f'{medfile} can not be recognized by viewer application'
        logger.error(errmsg)
        serviceHistory.append(f"{procts.action_at()},openmed,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    err = open_med_with_cytoinsights(medfile)
    errstat = 'completed' if err['code'] == 0 else 'failed'
    serviceHistory.append(f"{procts.action_at()},openmed,{request.client.host},{errstat},{procts.consumed_time()},{err['data']}")
    return err

@localapi.get('/summarize', summary='summarize cells count to CSV', include_in_schema=False)
async def summarize_cells_count(
    category: str,
    request: Request,
    aixpath: Optional[str] = Query(None, description='specified folder for summarizing')
):
    """ local private endpoint: summarize analyzed metadata to CSV """
    procts = TSaction()
    if aixpath and (not os.path.isdir(aixpath)):
        errmsg = f"{aixpath} is not a folder"
        serviceHistory.append(f"{procts.action_at()},summarize,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    csvfname = ''
    workpath = aixpath if aixpath else ''
    if category.lower() in ['urine', 'thyroid']:
        csvfname = summarize_cell_counts_to_csv(category, workpath)
    if not csvfname:
        errmsg = f'can not find any .aix file in {aixpath}'
        serviceHistory.append(f"{procts.action_at()},summary,{request.client.host},failed,{procts.consumed_time()},{errmsg}")
        raise HTTPException(status_code=404, detail=errmsg)
    serviceHistory.append(f"{procts.action_at()},summary,{request.client.host},completed,{procts.consumed_time()},{csvfname}")
    return f'{csvfname} completed!'
