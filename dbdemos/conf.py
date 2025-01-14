import json
import requests
from datetime import date
import re

def merge_dict(a, b, path=None):
    """merges dict b into a. Mutate a"""
    if path is None: path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dict(a[key], b[key], path + [str(key)])
            else:
                a[key] = b[key]
        else:
            a[key] = b[key]

class Conf():
    def __init__(self, username: str, workspace_url: str, pat_token: str, default_cluster_template: str = None, default_cluster_job_template = None,
                 repo_staging_path: str = None, repo_name: str = None, repo_url: str = None, branch: str = "master"):
        self.username = username
        self.workspace_url = workspace_url
        self.pat_token = pat_token
        self.headers = {"Authorization": "Bearer " + pat_token, 'Content-type': 'application/json'}
        self.default_cluster_template = default_cluster_template
        self.default_cluster_job_template = default_cluster_job_template
        self.repo_staging_path = repo_staging_path
        self.repo_name = repo_name
        self.repo_url = repo_url
        self.branch = branch

    def get_repo_path(self):
        return self.repo_staging_path+"/"+self.repo_name

class DBClient():
    def __init__(self, conf: Conf):
        self.conf = conf

    def clean_path(self, path):
        if path.startswith("http"):
            raise Exception(f"Wrong path {path}, use with api path directly (no http://xxx..xxx).")
        if path.startswith("/"):
            path = path[1:]
        if path.startswith("api/"):
            path = path[len("api/"):]
        return path

    def post(self, path: str, json: dict = {}):
        return requests.post(self.conf.workspace_url+"/api/"+self.clean_path(path), headers = self.conf.headers, json=json).json()

    def put(self, path: str, json: dict = {}):
        return requests.put(self.conf.workspace_url+"/api/"+self.clean_path(path), headers = self.conf.headers, json=json).json()

    def patch(self, path: str, json: dict = {}):
        return requests.patch(self.conf.workspace_url+"/api/"+self.clean_path(path), headers = self.conf.headers, json=json).json()

    def get(self, path: str, params: dict= {}):
        return requests.get(self.conf.workspace_url+"/api/"+self.clean_path(path), headers = self.conf.headers, params=params).json()

    def search_cluster(self, cluster_name: str, tags: dict):
        clusters = self.db.get("2.1/clusters/list")
        for c in clusters:
            if c['cluster_name'] == cluster_name:
                match = True
                #Check if all the tags are in the cluster conf
                for k, v in tags.items():
                    if k not in c['custom_tags'] or c['custom_tags'][k] != v:
                        match = False
                if match:
                    return c
        return None

    def find_job(self, name, offset = 0, limit = 25):
        r = self.get("2.1/jobs/list", {"limit": limit, "offset": offset})
        if 'jobs' in r:
            for job in r['jobs']:
                if job["settings"]["name"] == name:
                    return job
            if r['has_more']:
                return self.find_job(name, offset+limit, limit)
        return None

class DemoNotebook():
    def __init__(self, path: str, title: str, description: str, pre_run: bool = False, publish_on_website: bool = False,
                 add_cluster_setup_cell: bool = False, parameters: dict = {}):
        self.path = path
        self.title = title
        self.description = description
        self.pre_run = pre_run
        self.publish_on_website = publish_on_website
        self.add_cluster_setup_cell = add_cluster_setup_cell
        self.parameters = parameters

    def __repr__(self):
        return self.path

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__)

class DemoConf():
    def __init__(self, path: str, json_conf: dict):
        self.json_conf = json_conf
        self.notebooks = []
        self.cluster = json_conf.get('cluster', {})
        self.pipelines = json_conf.get('pipelines', [])
        self.init_job = json_conf.get('init_job', {})
        self.job_id = None
        self.run_id = None
        self.path = path
        self.name = json_conf['name']
        self.category = json_conf['category']
        self.title = json_conf['title']
        self.description = json_conf['description']
        self.tags = json_conf.get('tags', [])
        assert "bundle" in json_conf and json_conf["bundle"], "This demo isn't flaged for bundle. Please set bunde = True in the config file"

        for n in json_conf['notebooks']:
            add_cluster_setup_cell = n.get('add_cluster_setup_cell', False)
            params = n.get('parameters', {})
            self.notebooks.append(DemoNotebook(n['path'], n['title'], n['description'], n['pre_run'], n['publish_on_website'], add_cluster_setup_cell, params))

    def __repr__(self):
        return self.path + "("+str(self.notebooks)+")"

    def add_notebook(self, notebook):
        self.notebooks.append(notebook)
        #TODO: this isn't clean, need a better solution
        self.json_conf["notebooks"].append(notebook.__dict__)

    def set_pipeline_id(self, id, uid):
        j = json.dumps(self.init_job)
        j = j.replace("{{DYNAMIC_DLT_ID_"+id+"}}", uid)
        self.init_job = json.loads(j)

    def get_job_name(self):
        return "field-bundle_"+self.name

    def get_notebooks_to_run(self):
        return [n for n in self.notebooks if n.pre_run]

    def get_notebooks_to_publish(self):
        return [n for n in self.notebooks if n.publish_on_website]

    def get_bundle_path(self):
        return self.get_bundle_root_path() + "/install_package"

    def get_bundle_dashboard_path(self):
        return self.get_bundle_root_path() + "/dashboards"

    def get_bundle_root_path(self):
        return "dbdemos/bundles/"+self.name

    def get_minisite_path(self):
        return self.get_bundle_root_path() + "/minisite"


class ConfTemplate:
    def __init__(self, username, demo_name, demo_folder = ""):
        self.username = username
        self.demo_name = demo_name
        self.demo_folder = demo_folder

    def template_TODAY(self):
        return date.today().strftime("%Y-%m-%d")

    def template_CURRENT_USER(self):
        return self.username

    def template_CURRENT_USER_NAME(self):
        name = self.username[:self.username.rfind('@')]
        name = re.sub("[^A-Za-z0-9]", '_', name)
        return name

    def template_DEMO_NAME(self):
        return self.demo_name

    def template_DEMO_FOLDER(self):
        return self.demo_folder

    def replace_template_key(self, text: str):
        for key in set(re.findall(r'\{\{(.*?)\}\}', text)):
            if not key.startswith("DYNAMIC"):
                func = getattr(self, f"template_{key}")
                replacement = func()
                text = text.replace("{{"+key+"}}", replacement)
        return text