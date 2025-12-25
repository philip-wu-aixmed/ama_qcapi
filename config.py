import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
import time
from functools import lru_cache
from loguru import logger

## process time calculation
class TSaction:
    def __init__(self):
        self.__actiontime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self.__actionstart = time.perf_counter()
    def elapsed_time(self):
        return time.perf_counter()-self.__actionstart
    def consumed_time(self):
        seconds = time.perf_counter()-self.__actionstart
        mm, ss = divmod(seconds, 60)
        hh, mm = divmod(mm, 60)
        return f'{int(hh):02}:{int(mm):02}:{int(ss):02}{str(ss%1)[1:5]}'
    def action_at(self):
        return self.__actiontime

class Settings(BaseSettings):
    # APP configuration
    APP_NAME: str = 'AMA_UTILITIES'
    APP_VERSION: str = 'EMPTY'
    APP_DESCRIPTION: str = 'EMPTY'
    # SERVICE configuration
    API_HOST: str = '0.0.0.0'
    API_PORT: int = 5025
    SSL_ENABLED: bool = True
    SSL_KEYFILE: Optional[str] = r'.\certs\localhost.key'
    SSL_CERTFILE: Optional[str] = r'.\certs\localhost.crt'
    CORS_ORIGINS: List[str] = ["*"]
    # SECURITY configuration
    REQUEST_KEY: str = 'EMPTY'
    SECRET_KEY: str = 'empty'
    ALGORITHM: str = 'empty'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ACCESS_TOKEN_EXPIRE_DAYS: int = 1
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ACCESS_AVAILABLE_DOMAIN: List[str] = ['aixmed.com']
    # ENVIRONMENT configuration
    #DRIVEX_HOME: str = r'X:\CCH_scanner'         # scanner shared folder
    DRIVEY_HOME: str = r'Y:\CCH_scanner\medaix'  # on-premise image storage
    DRIVEY_URL: str = r'\\192.168.42.33\Auto Inference Backup'
    Y_USERNAME: str = 'aibadmin'
    Y_PASSWORD: str = 'aibadmin12345'
    AMAQC_HOME: str = r'E:\ama_qcapi\this_scanner'  # local working folders
    #DECART_PATH: str = r"C:\Program Files\WindowsApps\com.aixmed.decart_2.8.14.0_x64__pkjfmh18q18h8"
    #DECART_YAML: str = r"C:\ProgramData\DeCart\config.yaml"
    ENDPOINT_SLIDEINFO: str = "http://192.168.42.115:5025/v1/slideinfo?slide_id="
    # DUMMY ADMIN for CCH
    DUMMY_ADMIN: str = 'empty'
    DUMMY_EMAIL: str = 'empty'
    DUMMY_SLIDE: str = 'empty'
    #
    LOGFNAME: str = 'qcapi.log'
    ENVIRONMENT: str = 'production'
    ENVPATH: str = r'C:\Users\user\AppData\Local\ama_qcapi'
    # 
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.getenv('localappdata'), 'ama_qcapi', '.env'),
        extra='ignore'
    )
    #print(model_config)

class requestLOG:
    def __init__(self):
        self.logservice = os.path.join(os.getenv('LOCALAPPDATA'), 'ama_qcapi', 'request-history.csv')
        if os.path.exists(self.logservice):
            return
        header = 'datetime, request, requestor, status, consumed_time, note'
        try:
            with open(self.logservice, 'a', encoding='utf-8') as rlog:
                rlog.write(header+'\n')
        except Exception as e:
            logger.error(f'requestLOG.init failed: {e}')

    def append(self, record):
        try:
            with open(self.logservice, 'a', encoding='utf-8') as rlog:
                rlog.write(record+'\n')
        except Exception as e:
            logger.error(f'requestLOG.append failed: {e}')

@lru_cache()
def get_settings():
    return Settings()

# init settings
MYENV = get_settings()
serviceHistory = requestLOG()

##---------------------------------------------------------
# 📝 logging to %localappdata% using loguru
##---------------------------------------------------------
def initLogger(loglevel):
    # init logger with loguru
    logfname = os.path.join(os.getenv('LOCALAPPDATA'), 'ama_qcapi', MYENV.LOGFNAME)
    log_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <blue>Line {line: >4} ({file}):</blue> | <b>{message}</b>"
    logger.add(logfname, rotation='4 MB', level=loglevel, format=log_format, colorize=False, backtrace=True, diagnose=True)
    logger.debug(f'logfile is {logfname}')
