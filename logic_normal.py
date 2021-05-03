# -*- coding: utf-8 -*-
#########################################################
# python
import os
import sys
#sys.setdefaultencoding('utf-8')
import datetime
import traceback
import threading
import re
import subprocess
import shutil
import json
import ast
import time
import urllib
import rclone

# sjva 공용
from framework import app, db, scheduler, path_app_root, celery
from framework.job import Job
from framework.util import Util
from system.model import ModelSetting as SystemModelSetting
from framework.logger import get_logger

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting, ModelItem

import cgitb
cgitb.enable(format='text')

try:
    import google_auth_oauthlib.flow
except ImportError as e:
    os.system('pip install google-auth-oauthlib')
    import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import requests
#from urlparse import urlparse
from urllib.parse import urlparse
import json
from googleapiclient.http import MediaFileUpload
import httplib2
from oauth2client.client import GoogleCredentials

class LogicNormal(object):
    new_access_token = None
    expires_at = None

    @staticmethod
    @celery.task
    def scheduler_function():
        try:
            #logger.debug("youtube upload start!")
            client_id = ModelSetting.get('client_id')
            client_secret = ModelSetting.get('client_secret')
            access_token = ModelSetting.get('access_token')
            refresh_token = ModelSetting.get('refresh_token')
            category_id = ModelSetting.get('category_id')
            privacy_status = ModelSetting.get('privacy_status')
            upload_path = ModelSetting.get('upload_path')
            complete_path = ModelSetting.get('complete_path')
            redirect_uri = ModelSetting.get('redirect_uri')

            #logger.debug("client_id : %s", client_id)
            #logger.debug("client_secret : %s", client_secret)
            #logger.debug("access_token : %s", access_token)
            #logger.debug("refresh_token : %s", refresh_token)
            #logger.debug("upload_path : %s", upload_path)
            #logger.debug("complete_path : %s", complete_path)
            #logger.debug("redirect_uri : %s", redirect_uri)
            if client_id != '' and client_secret != '' and refresh_token != '' and upload_path != '' and complete_path != '' and redirect_uri != '':
                logger.debug("=========== SCRIPT START ===========")
                LogicNormal.refresh_token(client_id, client_secret, refresh_token, redirect_uri)
                LogicNormal.youtube_upload(upload_path, complete_path, client_id, client_secret, refresh_token, category_id, privacy_status)
                logger.debug("=========== SCRIPT END ===========")
        except Exception as e:
            logger.error('Exception:%s', e)
            logger.error(traceback.format_exc())

    
    @staticmethod
    def refresh_token(client_id, client_secret, refresh_token, redirect_uri):
        logger.debug("=========== refresh_token() START ===========")
        auth_url = "https://accounts.google.com/o/oauth2/token"
        redirect_uri = urlparse(redirect_uri)
        data = {
            "client_id" : client_id,
            "client_secret" : client_secret,
            "refresh_token" : refresh_token,
            "redirect_uri" : redirect_uri,
            "grant_type" : "refresh_token"
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}
        
        response = requests.post(auth_url, data=data, headers=headers)
        status_code = response.status_code
        #logger.debug("status_code : %s", response.status_code)
        #logger.debug("response.text : %s", response.text)
        if status_code == 200:
            json_data = json.loads(response.text)
            access_token = json_data["access_token"]
            expires_in = json_data["expires_in"]
            #logger.debug("new_access_token : %s", access_token)
            #logger.debug("expires_in : %s", expires_in)
            ModelSetting.set('access_token', access_token)
            LogicNormal.new_access_token = access_token
            LogicNormal.expires_at = expires_in
        logger.debug("=========== refresh_token() END ===========")


    @staticmethod
    def youtube_upload(upload_path, complete_path, client_id, client_secret, refresh_token, category_id, privacy_status):
        logger.debug("=========== youtube_upload() START ===========")
        #완료 폴더 없는 경우 생성
        if not os.path.isdir(complete_path): 
            os.makedirs(complete_path)
        #전달받은 path 경로에 / 없는 경우 예외처리
        if upload_path.rfind("/")+1 != len(upload_path):
            upload_path = upload_path+'/'
        
        if complete_path.rfind("/")+1 != len(complete_path):
            complete_path = complete_path+'/'

        os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
        api_service_name = "youtube"
        api_version = "v3"
        
        #권한설정
        user_agent = ""
        credentials = GoogleCredentials(
            LogicNormal.new_access_token,
            client_id,
            client_secret,
            refresh_token,
            LogicNormal.expires_at,
            "https://accounts.google.com/o/oauth2/token",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.105 Safari/537.36",
            revoke_uri=None
        )
        
        youtube = googleapiclient.discovery.build(api_service_name, api_version, credentials=credentials)
        
        #검색 제외 리스트
        exclude = ['@eaDir']
        #이동할 파일 조회(파일, 폴더내 파일)
        fileList = os.listdir(upload_path)
        #logger.debug("upload_path : %s", upload_path)
        for file in fileList:
            logger.debug("file : %s", upload_path+file)
            mvBool = True
            for ex in exclude:
                #시스템폴더 패스
                if ex == file:
                    mvBool = False
            #예외파일명 아니면 이동처리
            if mvBool:
                #파일이동처리
                if os.path.isfile(upload_path+file):
                    #logger.debug("target file name : %s", file)
                    title_name = os.path.splitext(file)[0]
                    now = datetime.datetime.now()
                    nowDatetime = now.strftime('%Y-%m-%d_%H%M%S')
                    title_name += "_"+nowDatetime
                    #logger.debug("title_name : %s", title_name)
                    request = youtube.videos().insert(
                        part="snippet,status",
                        body={
                            "snippet": {
                                "categoryId": category_id,
                                "description": "Description of uploaded video.",
                                "title": title_name
                            },
                            "status": {
                                "privacyStatus": privacy_status
                            }
                        },
                        
                        # TODO: For this request to work, you must replace "YOUR_FILE"
                        #       with a pointer to the actual file you are uploading.
                        media_body=MediaFileUpload(upload_path+file)
                    )
                    response = request.execute()
                    logger.debug("video.id : %s", response["id"])
                    #sucess upload -> file_move
                    shutil.move(upload_path+file, complete_path+file)
                    time.sleep(3)
                    
        logger.debug("=========== youtube_upload() END ===========")