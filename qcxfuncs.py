import os, glob
import gzip
import csv
import json
from pathlib import Path
import platform
import subprocess
import time
from loguru import logger
import win32wnet, pywintypes
from config import MYENV

## -------------------------------------------------------------- 
##  global preset working folders 
## -------------------------------------------------------------- 
class QCmagic:
    def __init__(self, magic_s, magic_a):
        self.__magic_suspicious = magic_s
        self.__magic_atypical = magic_a
        self.__magic_threshold = 0.4
    def setQCmagicnumber(self, s, a):
        self.__magic_suspicious = s
        self.__magic_atypical = a
    def getQCmagicS(self):
        return self.__magic_suspicious
    def getQCmagicA(self):
        return self.__magic_atypical
    def setScoreThreshold(self, tagscore):
        self.__magic_threshold = tagscore
    def getScoreThreshold(self):
        return self.__magic_threshold

qcMAGIC = QCmagic(6, 8)

##---------------------------------------------------------
## misc tools ♚: is NET drives still connected?? re-connect once if lost connection
##---------------------------------------------------------
def isNetConnectionAlive(drivehome):
    reconn = False
    driveletter = drivehome[:2]
    if os.path.exists(driveletter) == False:
        reconn = True
    else:
        if os.path.exists(drivehome) == False:
            logger.trace(f'{driveletter} is connected, but not connected to {drivehome}, need to re-connect')
            win32wnet.WNetCancelConnection2(driveletter, 1, True)
            reconn = True
    if reconn:  ## reconnect remote Windows computer
        ## try re-connect 
        try:
            win32wnet.WNetAddConnection2(0, driveletter, MYENV.DRIVEY_URL, None, MYENV.Y_USERNAME, MYENV.Y_PASSWORD)
        except pywintypes.error as e:
            logger.error(f'connection error: {e} ({drivehome})')
        else:
            logger.info(f'{drivehome} is re-connected to {driveletter}')
    # 
    return os.path.exists(drivehome)

##---------------------------------------------------------
## misc tools ♛: get file stat of .med file
##---------------------------------------------------------
def get_st_mtime(slide_type, slide_id):
    medfile = os.path.join(MYENV.DRIVEY_HOME, slide_type.lower(), slide_id)
    fstat = os.stat(medfile)
    return fstat.st_mtime

##---------------------------------------------------------
## misc tools ♞: change the tag score for QC criteria
##---------------------------------------------------------
def changeScoreCriteria4QC(score):
    logger.info(f'current score criteria is: {qcMAGIC.getScoreThreshold()}')
    qcMAGIC.setScoreThreshold(score)
    return True

##---------------------------------------------------------
## misc tools ♜: change the magic number for QC criteria
##---------------------------------------------------------
def changeMagicNumber4QC(s, a):
    logger.info(f'current magic number is suspicious:{qcMAGIC.getQCmagicS()}, atypical:{qcMAGIC.getQCmagicA()}')
    qcMAGIC.setQCmagicnumber(s, a)
    return True

##---------------------------------------------------------
# misc tools ♝: get current magic numbers
##---------------------------------------------------------
def getCurrentMagicNumber():
    magic = []
    magic.append(qcMAGIC.getQCmagicS())
    magic.append(qcMAGIC.getQCmagicA())
    magic.append(qcMAGIC.getScoreThreshold())
    return magic

##---------------------------------------------------------
## core tools ♠︎: retrieve .aix
##---------------------------------------------------------
def getMetadataFromAIX(aixfile):
    gaix = gzip.GzipFile(mode='rb', fileobj=open(aixfile, 'rb'))
    aixdata = gaix.read()
    gaix.close()
    aixjson = json.loads(aixdata)
    ## here is for decart version 2.x.x
    aixinfo = aixjson.get('model', {})
    aixcell = aixjson.get('graph', {})
    return aixinfo, aixcell

##---------------------------------------------------------
## core tools ♣︎: parse .aix
##---------------------------------------------------------
def getTargetCellsFromAIX(aixfile):
    aixinfo, aixcell = getMetadataFromAIX(aixfile)
    thismodel = aixinfo.get('Model')
    allCells = []
    if thismodel == 'AIxURO':
        categories = ['background', 'nuclei', 'suspicious', 'atypical', 'benign',
                      'other', 'tissue', 'degenerated']
        cellsCount = [0 for _ in range(len(categories))]
        nulltags = [0.0 for _ in range(14)]
        for jj in range(len(aixcell)):
            thiscell = {}
            cbody = aixcell[jj][1].get('children', '')
            if cbody == '':
                continue
            for kk in range(len(cbody)):
                cdata = cbody[kk][1].get('data', '')
                if cdata == '':
                    continue
                category = cdata.get('category', -1)
                if category >= 0 and category <= len(categories):
                    cellsCount[category] += 1
                else:
                    logger.error(f'{os.path.basename(aixfile)} has unknown cell category (ID: {category})')
                thiscell['cellname'] = cbody[kk][1]['name']
                thiscell['category'] = category
                thiscell['segments'] = cbody[kk][1]['segments']
                thiscell['ncratio'] = cdata.get('ncRatio', 0.0)
                thiscell['probability'] = cdata.get('prob', 0.0)
                thiscell['score'] = cdata.get('score', 0.0)
                thiscell['traits'] = cdata.get('tags', nulltags)
                allCells.append(thiscell)
        cellslist = sorted(allCells, key=lambda x: (-x['category'], x['score']), reverse=True)
        ## whatif too old version of AIxURO model ???
        if 'ModelArchitect' in aixinfo:
            ## decart 2.0.x and decart 2.1.x
            numNuclei, numAtypical, numBenign = cellsCount[3], cellsCount[1], cellsCount[0]
            cellsCount[0], cellsCount[4] = 0, numBenign
            cellsCount[1], cellsCount[3] = numNuclei, numAtypical
            logger.warning(f"{os.path.basename(aixfile)} was inference with {aixinfo.get('Model')}_{aixinfo.get('ModelVersion')}")
    elif thismodel == 'AIxTHY':
        if aixinfo['ModelVersion'][:6] in ['2025.2']:
            categories = ['background', 'follicular', 'oncocytic', 'epithelioid', 'lymphocytes', 
                          'histiocytes', 'colloid', 'unknown']
        else:
            categories = ['background', 'follicular', 'hurthle', 'histiocytes', 'lymphocytes', 
                          'colloid', 'multinucleatedGaint', 'psammomaBodies']
        cellsCount = [0 for _ in range(len(categories))]
        nulltags = [0.0 for _ in range(20)]
        for jj in range(len(aixcell)):
            thiscell = {}
            cbody = aixcell[jj][1].get('children', '')
            if cbody == '':
                continue
            for kk in range(len(cbody)):
                cdata = cbody[kk][1].get('data', '')
                if cdata == '':
                    continue
                category = cdata.get('category', -1)
                if category >= 0 and category <= len(categories):
                    cellsCount[category] += 1
                else:
                    logger.error(f'{os.path.basename(aixfile)} has unknown cell category (ID: {category})')
                thiscell['cellname'] = cbody[kk][1]['name']
                thiscell['category'] = category
                thiscell['segments'] = cbody[kk][1]['segments']
                thiscell['probability'] = cdata.get('prob', 0.0)
                thiscell['score'] = cdata.get('score', 0.0)
                thiscell['traits'] = cdata.get('tags', nulltags)
                allCells.append(thiscell)
        cellslist = sorted(allCells, key=lambda x: (-x['category'], x['score']), reverse=True)
    return aixinfo, cellslist, cellsCount

##---------------------------------------------------------
## core tools ♥︎: count thyroid traits
##---------------------------------------------------------
def countNumberOfTHYtraits(tclist, maxTraits, threshold=None):
    traitCount = [0 for i in range(maxTraits)]
    if not threshold:
        threshold = qcMAGIC.getScoreThreshold()
    howmany = len(tclist)
    if howmany == 0:
        logger.error(f'empty cell list in countNumberOfTHYtraits()')
        return traitCount
    for i in range(howmany):
        celltraits = tclist[i]['traits']
        for j in range(len(tclist[i]['traits'])):
            if celltraits[j] >= threshold:
                traitCount[j] += 1
    return traitCount

##---------------------------------------------------------
## api function: query slidename of all analyzed images
##---------------------------------------------------------
def queryAllSlideName(slide_type):
    if isNetConnectionAlive(MYENV.DRIVEY_HOME) == False:
        return {'code': -1, 'data': 'lost connection to image storage'}
    folder = os.path.join(MYENV.DRIVEY_HOME, slide_type.lower())
    logger.trace(f'starting queryAllSlideName({slide_type})...')
    medfiles = glob.glob(os.path.join(folder, '*.med'))
    namelist = []
    for _, fmed in enumerate(medfiles):
        faix = fmed.replace('.med', '.aix')
        #logger.trace(f'{fmed} <=> {faix}')
        if os.path.exists(faix):
            namelist.append(os.path.splitext(os.path.basename(fmed))[0])
    logger.info(f'found {len(namelist)} {slide_type} slides in {folder}')
    return {'code': 0, 'data': namelist}

##---------------------------------------------------------
## api function: query analyzed metadata for QC
##---------------------------------------------------------
def queryQCresult4slide(slide_type, slide_id, out_ver):
    if isNetConnectionAlive(MYENV.DRIVEY_HOME) == False:
        return {'code': -1, 'data': {}}
    ## magic number for urine criteria
    magic_suspicious = qcMAGIC.getQCmagicS()
    magic_atypical   = qcMAGIC.getQCmagicA()
    magic_threshold  = qcMAGIC.getScoreThreshold()
    ##
    aixmeta = {}
    aixmeta['medname'] = f'{slide_id}.med'
    if MYENV.DRIVEY_URL[0:1].isalpha():
        aixmeta['medpath'] = os.path.join(MYENV.DRIVEY_HOME, slide_type.lower())
    else:
        aixmeta['medpath'] = os.path.join(MYENV.DRIVEY_URL, MYENV.DRIVEY_HOME[2:], slide_type.lower())
    logger.debug(f'DRIVEY_URL:{MYENV.DRIVEY_URL}, DRIVEY_HOME:{MYENV.DRIVEY_HOME}=>{os.path.join(MYENV.DRIVEY_URL, MYENV.DRIVEY_HOME, slide_type)}')
    logger.trace(f'starting queryQCresult4slide({slide_type}, {slide_id})...')
    ##
    medfile = os.path.join(aixmeta['medpath'], aixmeta['medname'])
    if os.path.exists(medfile) == False:
        logger.error(f'{medfile} does not exist')
        return {'code': -2, 'data': {}}
    
    aixfile = medfile.replace('.med', '.aix')
    aixinfo, cellslist, cellscount = getTargetCellsFromAIX(aixfile)
    signals = ['red', 'green']
    aixmeta['signal'] = [signals[1] for _ in range(4)] if out_ver == 1 else [signals[1] for _ in range(2)]
    if aixinfo['Model'] == 'AIxURO':
        #aixmeta['rawdata'] = f'Suspicious: {cellscount[2]}; Atypical: {cellscount[3]}; Benign: {cellscount[4]}; Degenerated: {cellscount[7]}'
        aixmeta['rawdata'] = f'Suspicious: {cellscount[2]}; Atypical: {cellscount[3]}'
        if cellscount[3] >= magic_atypical:
            if cellscount[2] >= magic_suspicious:
                if out_ver == 0:
                    aixmeta['signal'][0], aixmeta['signal'][1] = signals[0], signals[0]
                else:
                    aixmeta['signal'][0] = signals[0]
                aixmeta['refnote'] = '' #'High likelihood of SHGUC or HGUC diagnosis'
            else:
                if out_ver == 1:
                    aixmeta['signal'][1] = signals[0]
                aixmeta['refnote'] = '' #'Extreme and rare case, less likely in real world'
        else:
            if cellscount[2] >= magic_suspicious:
                if out_ver == 0:
                    aixmeta['signal'][1] = signals[0]
                else:
                    aixmeta['signal'][2] = signals[0]
                aixmeta['refnote'] = '' #'Possible diagnosis of AUC; clinical information may be referenced to support the diagnosis'
            else:
                if out_ver == 0:
                    aixmeta['signal'][0] = signals[0]
                else:
                    aixmeta['signal'][3] = signals[0]
                aixmeta['refnote'] = '' #'Likely benign (NHGUC); may be excluded from further review'
    elif aixinfo['Model'] == 'AIxTHY':
        ## QC criteria for thyroid image is not defined yet, here is only for test
        sum_of_cells = sum(cellscount[j] for j in range(1, len(cellscount)))
        percentage_of_follicular = 0.0 if sum_of_cells == 0 else cellscount[1]/sum_of_cells
        if aixinfo['ModelVersion'][:6] in ['2025.2']:
            percentage_of_collid = 0.0 if sum_of_cells == 0 else cellscount[6]/sum_of_cells
        else:
            percentage_of_collid = 0.0 if sum_of_cells == 0 else cellscount[5]/sum_of_cells
        aixmeta['rawdata'] = f'Follicular: {cellscount[1]}; Hurthle: {cellscount[2]}; '
        aixmeta['rawdata'] += f'Histiocytes: {cellscount[3]}; Lymphocytes: {cellscount[4]}; '
        aixmeta['rawdata'] += f'Colloid: {cellscount[5]}'
        NUMofTags = 20 if aixinfo['ModelVersion'][:6] in ['2025.2'] else 8
        traits = countNumberOfTHYtraits(cellslist, NUMofTags)
        if '2025.2' in aixinfo['ModelVersion']:
            traitCount = len(list(filter(lambda x: x['traits'][8] >= magic_threshold and x['category'] == 1, cellslist)))
            traits_criteria = traitCount > 0
            traitcount = f'Microfollicles: {traits[2]}'
        elif '2024.2' in aixinfo['ModelVersion']:
            traitCount = len(list(filter(lambda x: x['traits'][4] >= magic_threshold and x['category'] == 1, cellslist)))
            traits_criteria = traitCount > 0
            traitcount = f'Microfollicles: {traits[0]}; Papillae: {traits[1]}; Pale nuclei: {traits[2]}; '
            traitcount += f'Grooving: {traits[3]}; Pseudoinclusions: {traits[4]}; '
            traitcount += f'Marginally placed micronucleoli: {traits[5]}; '
            traitcount += f'Plasmacytoid or spindled: {traits[6]}; Salt and pepper: {traits[7]}'
        #
        if (percentage_of_follicular > 0.7) and (percentage_of_collid > 0.5):
            aixmeta['signal'][0] = signals[0]
        if traits_criteria:
            aixmeta['signal'][1] = signals[1]
        aixmeta['refnote'] = f'Traits Count: {traitcount}'
    logger.info(f'found QC reference data for {slide_type} slides {slide_id}')
    ## add posix path
    #winpath = Path(aixmeta['medpath'])
    aixmeta['posixpath'] = Path(aixmeta['medpath']).as_posix()
    return {'code': 0, 'data': aixmeta}

##---------------------------------------------------------
## sub function: open .med file with CytoInsights
##---------------------------------------------------------
def openMEDwithCytoInsights(medfname):
    if platform.system() != 'Windows':
        return {'code': -1, 'data': 'only works in Windows'}
    viewer = r'C:\Program Files\AIxMed Cytology Viewer\AIxMed Cytology Viewer.exe'
    if os.path.exists(viewer):
        noviewer = False
    else:
        noviewer = True
        viewerpath = glob.glob(r'C:\Program Files\WindowsApps\cyto*')
        if len(viewerpath):
            viewer = f'{viewerpath[0]}\\app\\CytoInsights.exe'
            logger.trace(viewer)
            if os.path.exists(viewer) == False:
                logger.warning('CytoInsights does not exist!')
            else:
                noviewer = False
    err = {'code': 0, 'data': f'{medfname} opened'}
    if noviewer:    ## can't find cytoinsights
        subprocess.Popen(['start', '', medfname], shell=True)
    else:
        cannotrun = True
        try:
            subprocess.Popen([viewer, medfname])
            cannotrun = False
        except subprocess.CalledProcessError as e:
            logger.warning(f'CalledProcessError: {e}')
            err = {'code': -2, 'data': f'CalledProcessError: {e}'}
        except Exception as e:
            logger.warning(f'subprocess.Popen error: {e}')
            err = {'code': -3, 'data': f'subprocess.Popen error: {e}'}
        if cannotrun:
            subprocess.Popen(['start', '', medfname], shell=True)
    return err

##---------------------------------------------------------
## sub function: summarize cell counts to CSV
##---------------------------------------------------------
def summarizeCellCounts(slidetype, medpath=None):
    csvroot = os.path.join(MYENV.AMAQC_HOME, 'metadata')
    if os.path.exists(csvroot) == False:
        os.makedirs(csvroot)
    aixpath = medpath if medpath else os.path.join(MYENV.DRIVEY_HOME, slidetype.lower())
    aixfile = glob.glob(os.path.join(aixpath, f'*.aix'))
    logger.debug(f"found {len(aixfile)} .aix files in {aixpath}")
    csvfname = ''
    isUrine = True if slidetype.lower() == 'urine' else False
    if aixfile:
        ## summarize cell counts into CSV
        csvfname = f"{csvroot}\\summary_of_{slidetype}_cells_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        with open(csvfname, 'w', newline='') as outcsv:
            if isUrine:
                fields = ['slide_id', 'suspicious', 'atypical']
            else:
                fields = ['slide_id', 'follicular', 'hurthle', 'histiocytes', 'lymphocytes', 'colloid']

            ww = csv.DictWriter(outcsv, fieldnames=fields)
            ww.writeheader()
            for thisaix in aixfile:
                thisrow = {}
                if os.path.exists(thisaix):
                    modelinfo, _, cellscount = getTargetCellsFromAIX(thisaix)
                    thisrow['slide_id'] = os.path.splitext(os.path.basename(thisaix))[0]
                    if isUrine:
                        thisrow['suspicious'] = cellscount[2]
                        thisrow['atypical']   = cellscount[3]
                    elif modelinfo['ModelVersion'][:6] in ['2025.2']:
                        thisrow['follicular']    = cellscount[1]
                        thisrow['hurthle']       = cellscount[2]
                        thisrow['histiocytes']   = cellscount[5]
                        thisrow['lymphocytes']   = cellscount[4]
                        thisrow['colloid']       = cellscount[6]
                    else:
                        thisrow['follicular']    = cellscount[1]
                        thisrow['hurthle']       = cellscount[2]
                        thisrow['histiocytes']   = cellscount[3]
                        thisrow['lymphocytes']   = cellscount[4]
                        thisrow['colloid']       = cellscount[5]
                ww.writerow(thisrow)
    return os.path.basename(csvfname)
