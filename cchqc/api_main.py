""" CCHQC.v1.qcapi.cchqc.api_main
  main functio to launch API service with FastAPI
"""
import os
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from loguru import logger
from cchqc.config import MYENV, serviceHistory, TSaction, init_logger
from cchqc.amaqccch import qcapicch
from cchqc.secureqc import secure_qcapicch
from cchqc.subfuncs import localapi
from cchqc.dummycch import router_cchapi, router_cchimg
from cchqc.qcxfuncs import is_net_connection_alive

app = FastAPI(
    title = MYENV.APP_NAME,
    description = MYENV.APP_DESCRIPTION,
    version = MYENV.APP_VERSION,
    docs_url="/docs" if MYENV.ENVIRONMENT != 'production' else None,
    redoc_url="/redoc" if MYENV.ENVIRONMENT != 'production' else None
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=MYENV.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
app.include_router(qcapicch, prefix="/qc", tags=["APIs for CCH QC"])
app.include_router(secure_qcapicch, prefix="/cchqc", tags=["secured endpoints for CCH QC"])
app.include_router(localapi, prefix="/sub", tags=['sub functions'])
app.include_router(router_cchapi, prefix="/k8s-jwt-token/partner", tags=["mimic CCH APIs"])
app.include_router(router_cchimg, prefix="/expaimageapi", tags=["mimic query image info"])

@app.get("/", include_in_schema=False)
async def read_root():
    """
    dummy endpoint for testing ..... 🔒 ..... 🛡️ ..... 🚨 .....
    """
    return {
        "message": "localhost FastAPI SSL framework",
        "version": MYENV.APP_VERSION,
        "SSL enabled": MYENV.SSL_ENABLED
    }

@app.get('/health', summary='API service healthy check')
async def qcapi_health_check(request: Request):
    """
    API serivce health check
    """
    procts = TSaction()
    serviceHistory.append(f"{procts.action_at()},health,{request.client.host},completed,{procts.consumed_time()},n.a.")
    return {'status': 'healthy', 'timestamp': time.strftime("%Y-%m-%d %H:%M:%S",time.localtime())}

def start_qcapi(from_main=None):
    """ 🔒🛡️🚨
    launch API service
      :param from_main (bool): True if call from __main__ function
    """
    if from_main:
        log_level = 'TRACE'
        need_reload = True
    else:
        log_level = 'DEBUG'
        need_reload = False
    init_logger(log_level)
    ## check net connection before launching api service
    isconnected = False
    connectedts = TSaction()
    while True:
        if connectedts.elapsed_time() > 1800:   ## wait for max 30 minutes
            break
        if is_net_connection_alive(MYENV.DRIVEY_HOME):
            isconnected = True
            break
        time.sleep(60)
    if isconnected:
        key_file = os.path.join(os.getenv('localappdata'), MYENV.APP_NAME, MYENV.SSL_KEYFILE)
        certfile = os.path.join(os.getenv('localappdata'), MYENV.APP_NAME, MYENV.SSL_CERTFILE)
        uvicorn.run('cchqc.api_main:app', host=MYENV.API_HOST, port=MYENV.API_PORT,
                    ssl_keyfile=key_file,
                    ssl_certfile=certfile,
                    reload=need_reload)
    else:
        logger.error(f'[AMI_MAIN][ERROR] can not connect to {MYENV.DRIVEY_HOME}, pleasec contact with service team')

if __name__  == '__main__':
    start_qcapi(True)
    #initLogger('TRACE')
    #key_file = os.path.join(os.getenv('localappdata'), MYENV.APP_NAME, MYENV.SSL_KEYFILE)
    #certfile = os.path.join(os.getenv('localappdata'), MYENV.APP_NAME, MYENV.SSL_CERTFILE)
    #logger.debug(certfile)
    #print(key_file)
    #uvicorn.run('api_main:app', host=MYENV.API_HOST, port=MYENV.API_PORT,
    #            ssl_keyfile=key_file,
    #            ssl_certfile=certfile,
    #            reload=True)
