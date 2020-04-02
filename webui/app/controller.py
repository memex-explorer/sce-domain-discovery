import requests
from app import classifier
from flask import Blueprint, request, send_from_directory, jsonify
from flask_cors import CORS
import os
import subprocess

# Define Blueprint(s)
mod_app = Blueprint('application', __name__, url_prefix='/explorer-api')
CORS(mod_app)

k8s = os.getenv('RUNNING_KUBERNETES', 'true')


# Define Controller(s)
@mod_app.route('/')
def index():
    return send_from_directory('static/pages', 'index.html')

@mod_app.route('/classify/createnew/<model>', methods=['GET'])
def create_new_model(model):
    ## TODO need to deal with naming models
    print("here")
    #classifier.clear_model()
    classifier.new_model(model)
    return("done")


@mod_app.route('/classify/listmodels', methods=['GET'])
def list_models():
    return jsonify(classifier.get_models())


# POST Requests
@mod_app.route('/classify/update/<model>', methods=['POST'])
def build_model(model):
    ## TODO Specify model
    annotations = []
    data = request.get_json()
    for key, value in data.iteritems():
        annotations.append(int(value))
    #for item in data.split('&'):
    #    annotations.append(int(item.split('=')[1]))

    accuracy = classifier.update_model(model, annotations)
    return accuracy


@mod_app.route('/classify/upload/<model>', methods=['POST'])
def upload_model(model):
    ## TODO Specify model
    return classifier.import_model(model)


@mod_app.route('/classify/download/<model>', methods=['POST'])
def download_model(model):
    ## TODO Specify model
    return classifier.export_model(model)


@mod_app.route('/classify/exist/<model>', methods=['POST'])
def check_model(model):
    return classifier.check_model(model)

@mod_app.route('/classify/stats/<model>', methods=['GET'])
def model_stats(model):
    return classifier.check_model(model)

@mod_app.route('/cmd/crawler/exist/<model>', methods=['POST'])
def check_crawl_exists(model):
    ## TODO Specify model
    ## TODO FIX URL for scale out
    return requests.post("http://sparkler:6000/cmd/crawler/exist/").text


@mod_app.route('/cmd/crawler/crawl/<model>', methods=['POST'])
def start_crawl(model):
    content = request.json
    topn = "1000"
    topgrp = "256"
    sortby = "discover_depth asc, score asc"
    groupby = "group"
    serverdelay = "1000"
    fetchheaders = '''User-Agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Sparkler/${project.version}"
  Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
  Accept-Language: "en-US,en"'''
    activeplugins = """- urlfilter-regex
    - urlfilter-samehost
    """
    plugins = """urlfilter.regex:
    urlfilter.regex.file: regex-urlfilter.txt
  fetcher.jbrowser:
    socket.timeout: 3000
    connect.timeout: 3000    
    """

    if("topn" in content):
        topn = content.topn
    if("topgrp" in content):
        topgrp = content.topgrp
    if("sortby" in content):
        sortby = content.sortby
    if("groupby" in content):
        groupby = content.groupby
    if("serverdelay" in content):
        serverdelay = content.serverdelay
    if("fetchheaders" in content):
        fetchheaders = content.fetchheaders
    if("activeplugins" in content):
        activeplugins = content.activeplugins
    if("plugins" in content):
        plugins = content.plugins

    yml = """
crawldb.uri: http://localhost:8983/solr/crawldb
spark.master: local[*]
kafka.enable: false
kafka.listeners: localhost:9092
kafka.topic: sparkler_%s
generate.topn:  """+topn+"""
generate.top.groups: """+topgrp+"""
generate.sortby: \""""+sortby+"""\"
generate.groupby: \""""+groupby+"""\"
fetcher.server.delay: """+serverdelay+"""
fetcher.headers:
  """+fetchheaders+"""
plugins.active:
    """+activeplugins+"""
plugins:
  """+plugins
    print(yml)

    #cmd = ["echo", yml, ">", "/data/sparkler/conf/sparkler-default.yaml", "&&", "/data/sparkler/bin/sparkler.sh", "crawl", "-cdb", "http://sce-solr:8983/solr/crawldb", "-id", model]
    cmd = ["bash", "-c", "echo \'"+yml+"\' > /data/sparkler/conf/sparkler-default.yaml && /data/sparkler/bin/sparkler.sh crawl -cdb http://sce-solr:8983/solr/crawldb -id "+model]
    if k8s.lower() == "true":
        f=open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r")
        token =""
        if f.mode == 'r':
            token =f.read()

        requests.delete('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods/'+model+"crawl",headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)
        json = {"kind": "Pod", "apiVersion": "v1",
                "metadata": {"name": model+"crawl", "labels": {"run": model+"seed"}}, "spec": {
                "containers": [
                    {"name": model+"crawl", "image": "registry.gitlab.com/sparkler-crawl-environment/sparkler/sparkler:memex-dd", "command": cmd,
                     "resources": {}}], "restartPolicy": "Never", "dnsPolicy": "ClusterFirst"}, "status": {}}
        requests.post('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods', json=json, headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)
        return "crawl started"
    else:
        print("Removing old container")
        pcmd = ["docker", "rm", model+"crawl"]
        subprocess.call(pcmd)
        print("Running container")
        qcmd = ["docker", "run", "--network", "compose_default", "--name", model+"crawl", "registry.gitlab.com/sparkler-crawl-environment/sparkler/sparkler:memex-dd"] + cmd
        subprocess.Popen(qcmd)
        return "crawl started"

@mod_app.route('/cmd/crawler/crawl/<model>', methods=['DELETE'])
def stop_crawl(model):
    if k8s.lower() == "true":
        f=open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r")
        token =""
        if f.mode == 'r':
            token =f.read()

        requests.delete('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods/'+model+"crawl", headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)

        return "crawl ended"
    else:
        qcmd = ["docker", "stop", model+"crawl"]
        subprocess.call(qcmd)
        return "crawl ended"

@mod_app.route('/cmd/crawler/crawler/<model>', methods=['GET'])
def crawl_status(model):
    if k8s.lower() == "true":
        f = open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r")
        token = ""
        if f.mode == 'r':
            token = f.read()
        r = requests.get('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods', headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)
        return jsonify(r.json())
    else:
        qcmd = ["docker", "container", "ls", "--filter", "name="+model]
        o = subprocess.check_output(qcmd)

        if model in o.decode("utf-8"):
            return jsonify({"running": "true"})
        else:
            return jsonify({"running": "false"})



@mod_app.route('/cmd/crawler/int/<model>', methods=['POST'])
def kill_crawl_gracefully(model):
    if k8s.lower() == "true":
        f=open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r")
        token =""
        if f.mode == 'r':
            token =f.read()

        requests.delete('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods/'+model+"crawl", headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)

        return "crawl killed"
    else:
        qcmd = ["docker", "stop", model+"crawl"]
        subprocess.call(qcmd)
        return "crawl killed"

@mod_app.route('/cmd/crawler/kill/<model>', methods=['POST'])
def force_kill_crawl(model):
    if k8s.lower() == "true":
        f=open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r")
        token =""
        if f.mode == 'r':
            token =f.read()

        requests.delete('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods/'+model+"crawl", headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)

        return "crawl killed"
    else:
        qcmd = ["docker", "stop", model+"crawl"]
        subprocess.call(qcmd)
        return "crawl killed"


@mod_app.route('/cmd/seed/upload/<model>', methods=['POST'])
def upload_seed(model):
    print request.get_data()
    ## TODO Come up with a way of updating the uploaded data.
    classifier.save_seeds(model, request.get_data())
    seeds =  request.get_data().splitlines()
    urls = ",".join(seeds)
    cmd = ["/data/sparkler/bin/sparkler.sh", "inject", "-cdb", "http://sce-solr:8983/solr/crawldb", "-su", urls, "-id", model]
    if k8s.lower() == "true":
        f=open("/var/run/secrets/kubernetes.io/serviceaccount/token", "r")
        token =""
        if f.mode == 'r':
            token =f.read()
        requests.delete('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods/'+model+"seed",headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)
        json = {"kind": "Pod", "apiVersion": "v1",
                 "metadata": {"name": model+"seed", "labels": {"run": model+"seed"}}, "spec": {
                "containers": [
                    {"name": model+"seed", "image": "registry.gitlab.com/sparkler-crawl-environment/sparkler/sparkler:memex-dd", "command": cmd,
                     "resources": {}}], "restartPolicy": "Never", "dnsPolicy": "ClusterFirst"}, "status": {}}
        requests.post('https://kubernetes.default.svc.cluster.local/api/v1/namespaces/default/pods', json=json, headers={"content-type":"application/json", "Authorization": "Bearer "+token}, verify=False)
        return "seed urls uploaded"
    else:
        pcmd = ["docker", "rm", model+"seed"]
        qcmd = ["docker", "run", "--network", "compose_default", "--name", model+"seed", "registry.gitlab.com/sparkler-crawl-environment/sparkler/sparkler:memex-dd"] + cmd
        subprocess.call(pcmd)
        subprocess.Popen(qcmd)
        return "seed urls uploaded"
