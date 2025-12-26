""" Docstring for CCHQC.v1.qcapi.cchqc.qcxfuncs
  functions to provide analyzed metadata to QCAPI endpoints
"""
import os
import glob
import gzip
import csv
import json
from pathlib import Path
import platform
import subprocess
import time
from loguru import logger
import win32wnet
import pywintypes
from cchqc.config import MYENV

## --------------------------------------------------------------
##  global preset working folders
## --------------------------------------------------------------
class QCmagic:
    """ magic number for QC criteria """
    def __init__(self, magic_s, magic_a):
        self.__magic_suspicious = magic_s
        self.__magic_atypical = magic_a
        self.__magic_threshold = 0.4
    def setqc_magic_number(self, s, a):
        """ set magic number for both suspicious cell and atypical cell """
        self.__magic_suspicious = s
        self.__magic_atypical = a
    def getqc_magic_s(self):
        """ get suspicious magic number """
        return self.__magic_suspicious
    def getqc_magic_a(self):
        """ get atypical magic number """
        return self.__magic_atypical
    def set_score_threshold(self, tagscore):
        """ set score threshold """
        self.__magic_threshold = tagscore
    def get_score_threshold(self):
        """ get score threshold """
        return self.__magic_threshold

qcMAGIC = QCmagic(6, 8)

def is_net_connection_alive(drivehome):
    """ misc tools ♚
    is NET drives still connected?? re-connect once if lost connection
      :param drivehome: path in remote drive
    """
    reconn = False
    driveletter = drivehome[:2]
    if not os.path.exists(driveletter):
        reconn = True
    else:
        if not os.path.exists(drivehome):
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

def get_st_mtime(slide_type, slide_id):
    """ misc tools ♛
    get file stat of .med file
      :param slide_type: urine or thyroid
      :param slide_id: slide id
    """
    medfile = os.path.join(MYENV.DRIVEY_HOME, slide_type.lower(), slide_id)
    fstat = os.stat(medfile)
    return fstat.st_mtime

def change_qc_score_criteria(score):
    """ misc tools ♞
    change the tag score for QC criteria
      :param score: score to be updated
    """
    logger.info(f'current score criteria is: {qcMAGIC.get_score_threshold()}')
    qcMAGIC.set_score_threshold(score)
    return True

def change_qc_magic_number(s, a):
    """ misc tools ♜
    change the magic number for QC criteria
      :param s: magic number for suspicious cell
      :param a: magic number for atypical cell
    """
    logger.info(f'current magic number is suspicious:{qcMAGIC.getqc_magic_s()}, atypical:{qcMAGIC.getqc_magic_a()}')
    qcMAGIC.setqc_magic_number(s, a)
    return True

def get_current_magic_number():
    """ misc tools ♝: get current magic numbers """
    magic = []
    magic.append(qcMAGIC.getqc_magic_s())
    magic.append(qcMAGIC.getqc_magic_a())
    magic.append(qcMAGIC.get_score_threshold())
    return magic

def get_metadata_from_aix(aixfile):
    """ core tools ♠︎: retrieve .aix """
    gaix = gzip.GzipFile(mode='rb', fileobj=open(aixfile, 'rb'))
    aixdata = gaix.read()
    gaix.close()
    aixjson = json.loads(aixdata)
    ## here is for decart version 2.x.x
    aixinfo = aixjson.get('model', {})
    aixcell = aixjson.get('graph', {})
    return aixinfo, aixcell

def get_target_cells_from_aix(aixfile):
    """ core tools ♣︎: 
    parse .aix
      :param aixfile: .aix filename for parsing
    """
    aixinfo, aixcell = get_metadata_from_aix(aixfile)
    thismodel = aixinfo.get('Model')
    allcells = []
    if thismodel == 'AIxURO':
        categories = ['background', 'nuclei', 'suspicious', 'atypical', 'benign',
                      'other', 'tissue', 'degenerated']
        cellscount = [0 for _ in range(len(categories))]
        nulltags = [0.0 for _ in range(14)]
        for cell in aixcell:
            thiscell = {}
            cbody = cell[1].get('children', '')
            if cbody == '':
                continue
            for kkbody in cbody:
                cdata = kkbody[1].get('data', '')
                if not cdata:
                    continue
                category = cdata.get('category', -1)
                if category >= 0 and category <= len(categories):
                    cellscount[category] += 1
                else:
                    logger.error(f'{os.path.basename(aixfile)} has unknown cell category (ID: {category})')
                thiscell['cellname'] = kkbody[1]['name']
                thiscell['category'] = category
                thiscell['segments'] = kkbody[1]['segments']
                thiscell['ncratio'] = cdata.get('ncRatio', 0.0)
                thiscell['probability'] = cdata.get('prob', 0.0)
                thiscell['score'] = cdata.get('score', 0.0)
                thiscell['traits'] = cdata.get('tags', nulltags)
                allcells.append(thiscell)
        cellslist = sorted(allcells, key=lambda x: (-x['category'], x['score']), reverse=True)
        ## whatif too old version of AIxURO model ???
        if 'ModelArchitect' in aixinfo:
            ## decart 2.0.x and decart 2.1.x
            num_nuclei, num_atypical, num_benign = cellscount[3], cellscount[1], cellscount[0]
            cellscount[0], cellscount[4] = 0, num_benign
            cellscount[1], cellscount[3] = num_nuclei, num_atypical
            logger.warning(f"{os.path.basename(aixfile)} was inference with {aixinfo.get('Model')}_{aixinfo.get('ModelVersion')}")
    elif thismodel == 'AIxTHY':
        if aixinfo['ModelVersion'][:6] in ['2025.2']:
            categories = ['background', 'follicular', 'oncocytic', 'epithelioid', 'lymphocytes',
                          'histiocytes', 'colloid', 'unknown']
        else:
            categories = ['background', 'follicular', 'hurthle', 'histiocytes', 'lymphocytes',
                          'colloid', 'multinucleatedGaint', 'psammomaBodies']
        cellscount = [0 for _ in range(len(categories))]
        nulltags = [0.0 for _ in range(20)]
        for jjcell in aixcell:
            thiscell = {}
            cbody = jjcell[1].get('children', '')
            if not cbody:
                continue
            for kkbody in cbody:
                cdata = kkbody[1].get('data', '')
                if not cdata:
                    continue
                category = cdata.get('category', -1)
                if category >= 0 and category <= len(categories):
                    cellscount[category] += 1
                else:
                    logger.error(f'{os.path.basename(aixfile)} has unknown cell category (ID: {category})')
                thiscell['cellname'] = kkbody['name']
                thiscell['category'] = category
                thiscell['segments'] = kkbody[1]['segments']
                thiscell['probability'] = cdata.get('prob', 0.0)
                thiscell['score'] = cdata.get('score', 0.0)
                thiscell['traits'] = cdata.get('tags', nulltags)
                allcells.append(thiscell)
        cellslist = sorted(allcells, key=lambda x: (-x['category'], x['score']), reverse=True)
    else:
        cellslist = []
        logger.warning('does not support {thismodel}')
    return aixinfo, cellslist, cellscount

def count_number_of_thyroid_traits(tclist, max_traits, threshold=None):
    """ core tools ♥︎: 
    count thyroid traits
      :param tclist: cell list from .aix file
      :param max_traits:maximum number of traits
      :param threshold: criteria for counting trait
    """
    traitcount = [0 for i in range(max_traits)]
    if not threshold:
        threshold = qcMAGIC.get_score_threshold()
    howmany = len(tclist)
    if howmany == 0:
        logger.error('empty cell list in countNumberOfTHYtraits()')
        return traitcount
    for i in range(howmany):
        celltraits = tclist[i]['traits']
        for j in range(len(tclist[i]['traits'])):
            if celltraits[j] >= threshold:
                traitcount[j] += 1
    return traitcount

def query_all_slide_name(slide_type):
    """
    query slidename of all analyzed images
      :param slide_type: urine or thyroid
    """
    if not is_net_connection_alive(MYENV.DRIVEY_HOME):
        return {'code': -1, 'data': 'lost connection to image storage'}
    folder = os.path.join(MYENV.DRIVEY_HOME, slide_type.lower())
    logger.trace(f'starting query_all_slide_name({slide_type})...')
    medfiles = glob.glob(os.path.join(folder, '*.med'))
    namelist = []
    for _, fmed in enumerate(medfiles):
        faix = fmed.replace('.med', '.aix')
        #logger.trace(f'{fmed} <=> {faix}')
        if os.path.exists(faix):
            namelist.append(os.path.splitext(os.path.basename(fmed))[0])
    logger.info(f'found {len(namelist)} {slide_type} slides in {folder}')
    return {'code': 0, 'data': namelist}

def query_qcresult_for_slide(slide_type, slide_id, out_ver):
    """
    query analyzed metadata for QC
      :param slide_type: urine or thyroid
      :param slide_id: slide id
      :param out_ver: data format version for return data
    """
    if not is_net_connection_alive(MYENV.DRIVEY_HOME):
        return {'code': -1, 'data': {}}
    ## magic number for urine criteria
    magic_suspicious = qcMAGIC.getqc_magic_s()
    magic_atypical   = qcMAGIC.getqc_magic_a()
    magic_threshold  = qcMAGIC.get_score_threshold()
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
    if not os.path.exists(medfile):
        logger.error(f'{medfile} does not exist')
        return {'code': -2, 'data': {}}

    aixfile = medfile.replace('.med', '.aix')
    aixinfo, cellslist, cellscount = get_target_cells_from_aix(aixfile)
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
        num_of_tags = 20 if aixinfo['ModelVersion'][:6] in ['2025.2'] else 8
        traits = count_number_of_thyroid_traits(cellslist, num_of_tags)
        if '2025.2' in aixinfo['ModelVersion']:
            trait_count = len(list(filter(lambda x: x['traits'][8] >= magic_threshold and x['category'] == 1, cellslist)))
            traits_criteria = trait_count > 0
            traitcount = f'Microfollicles: {traits[2]}'
        elif '2024.2' in aixinfo['ModelVersion']:
            trait_count = len(list(filter(lambda x: x['traits'][4] >= magic_threshold and x['category'] == 1, cellslist)))
            traits_criteria = trait_count > 0
            traitcount = f'Microfollicles: {traits[0]}; Papillae: {traits[1]}; Pale nuclei: {traits[2]}; '
            traitcount += f'Grooving: {traits[3]}; Pseudoinclusions: {traits[4]}; '
            traitcount += f'Marginally placed micronucleoli: {traits[5]}; '
            traitcount += f'Plasmacytoid or spindled: {traits[6]}; Salt and pepper: {traits[7]}'
        else:   ## should not be here
            traits_criteria = False
            logger.warning(f"unknown {aixinfo['ModelVersion']}")
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
def open_med_with_cytoinsights(medfname):
    """
    open .med file with CytoInsights
      :param medfname: .med filename
    """
    if platform.system() != 'Windows':
        return {'code': -1, 'data': 'only works in Windows'}
    viewer = r'C:\Program Files\AIxMed Cytology Viewer\AIxMed Cytology Viewer.exe'
    if os.path.exists(viewer):
        noviewer = False
    else:
        noviewer = True
        viewerpath = glob.glob(r'C:\Program Files\WindowsApps\cyto*')
        if len(viewerpath) > 0:
            viewer = f'{viewerpath[0]}\\app\\CytoInsights.exe'
            logger.trace(viewer)
            if not os.path.exists(viewer):
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
            raise
        if cannotrun:
            subprocess.Popen(['start', '', medfname], shell=True)
    return err

def summarize_cell_counts_to_csv(slidetype, medpath=None):
    """
    summarize cell counts to CSV
      :param slidetype: urine or thyroid
      :param medpath: folder contains .aix/.med files
    """
    csvroot = os.path.join(MYENV.AMAQC_HOME, 'metadata')
    if not os.path.exists(csvroot):
        os.makedirs(csvroot)
    aixpath = medpath if medpath else os.path.join(MYENV.DRIVEY_HOME, slidetype.lower())
    aixfile = glob.glob(os.path.join(aixpath, '*.aix'))
    logger.debug(f"found {len(aixfile)} .aix files in {aixpath}")
    csvfname = ''
    is_urine = True if slidetype.lower() == 'urine' else False
    if aixfile:
        ## summarize cell counts into CSV
        csvfname = f"{csvroot}\\summary_of_{slidetype}_cells_{time.strftime('%Y%m%d_%H%M%S')}.csv"
        with open(csvfname, 'w', newline='', encoding='utf-8') as outcsv:
            if is_urine:
                fields = ['slide_id', 'suspicious', 'atypical']
            else:
                fields = ['slide_id', 'follicular', 'hurthle', 'histiocytes', 'lymphocytes', 'colloid']

            ww = csv.DictWriter(outcsv, fieldnames=fields)
            ww.writeheader()
            for thisaix in aixfile:
                thisrow = {}
                if os.path.exists(thisaix):
                    modelinfo, _, cellscount = get_target_cells_from_aix(thisaix)
                    thisrow['slide_id'] = os.path.splitext(os.path.basename(thisaix))[0]
                    if is_urine:
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
