#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import urllib
from uuid import uuid4

import boto3
import requests
from botocore.client import Config
from flask import Flask, request

boto3.set_stream_logger('boto3.resources', logging.DEBUG)

authorize_url = "http://localhost:8080/auth/realms/minio/protocol/openid-connect/auth"
token_url = "http://localhost:8080/auth/realms/minio/protocol/openid-connect/token"

# callback url specified when the application was defined
callback_uri = "http://localhost:8000/oauth2/callback"

# keycloak id and secret
client_id = 'account'
client_secret = 'daaa3008-80f0-40f7-80d7-e15167531ff0'

sts_client = boto3.client(
    'sts',
    region_name='us-east-1',
    use_ssl=False,
    endpoint_url='http://localhost:9000',
)

app = Flask(__name__)


@app.route('/')
def homepage():
    text = '<a href="%s">Authenticate with keycloak</a>'
    return text % make_authorization_url()


def make_authorization_url():
    # Generate a random string for the state parameter
    # Save it for use later to prevent xsrf attacks

    state = str(uuid4())
    params = {"client_id": client_id,
              "response_type": "code",
              "state": state,
              "redirect_uri": callback_uri,
              "scope": "openid"}

    url = authorize_url + "?" + urllib.parse.urlencode(params)
    return url


@app.route('/oauth2/callback')
def callback():
    error = request.args.get('error', '')
    if error:
        return "Error: " + error

    authorization_code = request.args.get('code')

    data = {'grant_type': 'authorization_code',
            'code': authorization_code, 'redirect_uri': callback_uri}
    access_token_response = requests.post(
        token_url, data=data, verify=False, allow_redirects=False, auth=(client_id, client_secret))

    print('body: ' + access_token_response.text)

    # we can now use the access_token as much as we want to access protected resources.
    tokens = json.loads(access_token_response.text)
    access_token = tokens['access_token']

    response = sts_client.assume_role_with_web_identity(
        RoleArn='arn:aws:iam::123456789012:user/svc-internal-api',
        RoleSessionName='test',
        WebIdentityToken=access_token,
        DurationSeconds=3600
    )

    s3_resource = boto3.resource('s3',
                                 endpoint_url='http://localhost:9000',
                                 aws_access_key_id=response['Credentials']['AccessKeyId'],
                                 aws_secret_access_key=response['Credentials']['SecretAccessKey'],
                                 aws_session_token=response['Credentials']['SessionToken'],
                                 config=Config(signature_version='s3v4'),
                                 region_name='us-east-1')

    bucket = s3_resource.Bucket('testbucket')

    for obj in bucket.objects.all():
        print(obj)

    return "success"


if __name__ == '__main__':
    app.run(debug=True, port=8000)
