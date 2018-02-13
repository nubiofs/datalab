#!/usr/bin/env python
#
# Copyright 2018 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This file defines an end-to-end test that validates core functionality
# of the bundled CLI tool. This requires a GCP project in which the
# test will create, connect to, and delete Datalab instances.

import subprocess
import tempfile
import time
import unittest
import urllib2
import uuid


connection_msg = (
    'The connection to Datalab is now open and will '
    'remain until this command is killed.')
readme_url = 'http://localhost:8081/api/contents/datalab/docs/Readme.ipynb'
readme_header = 'Guide to Google Cloud Datalab'


def generate_unique_id():
    return uuid.uuid4().hex[0:12]


def call_gcloud(args):
    return subprocess.check_output(['gcloud'] + args)


class DatalabInstance(object):
    def __init__(self, test_run_id, project, zone):
        self.project = project
        self.zone = zone
        name_suffix = generate_unique_id()
        self.name = "test-instance-{0}-{1}".format(
            test_run_id, name_suffix)

    def __enter__(self):
        cmd = ['python', '-u', './tools/cli/datalab.py', '--quiet',
               '--project', self.project,
               '--zone', self.zone,
               '--verbosity', 'debug',
               'create', '--no-connect', self.name]
        print('Creating the instance "{}" with the command "{}"'.format(
            self.name, ' '.join(cmd)))
        subprocess.check_output(cmd)
        print('Status of the instance: "{}"'.format(self.status()))
        return self

    def __exit__(self, *unused_args, **unused_kwargs):
        cmd = ['python', '-u', './tools/cli/datalab.py', '--quiet',
               '--project', self.project,
               '--zone', self.zone,
               '--verbosity', 'debug',
               'delete', '--delete-disk', self.name]
        print('Deleting the instance "{}" with the command "{}"'.format(
            self.name, ' '.join(cmd)))
        subprocess.check_output(cmd)

    def status(self):
        cmd = ['python', '-u', './tools/cli/datalab.py', '--quiet',
               '--project', self.project,
               '--zone', self.zone,
               'list', '--filter',  "(name={})".format(self.name)]
        return subprocess.check_output(cmd)


class DatalabConnection(object):
    def __init__(self, project, zone, instance, stdout):
        self.project = project
        self.zone = zone
        self.instance = instance
        self.stdout = stdout

    def __enter__(self):
        cmd = ['python', '-u', './tools/cli/datalab.py', '--quiet',
               '--project', self.project, '--zone', self.zone,
               '--verbosity', 'debug',
               'connect', '--no-launch-browser', self.instance]
        self.process = subprocess.Popen(cmd, stdout=self.stdout)
        attempts = 0
        while attempts < 10:
            attempts += 1
            with open(self.stdout.name, "r") as written_stdout:
                if connection_msg in written_stdout.read():
                    return
            time.sleep(60)

    def __exit__(self, *unused_args, **unused_kwargs):
        self.process.terminate()
        self.process.communicate()


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.test_run_name = generate_unique_id()
        self.project = call_gcloud(
            ['config', 'get-value', 'core/project']).strip()
        self.zone = call_gcloud(
            ['config', 'get-value', 'compute/zone']).strip()
        if self.zone == '':
            self.zone = 'us-west1-a'
        print('Testing with in the zone {} under the project {}'.format(
            self.zone, self.project))

    def call_datalab(self, subcommand, args):
        cmd = ['python', '-u', './tools/cli/datalab.py', '--quiet',
               '--project', self.project,
               '--zone', self.zone, subcommand] + args
        print('Running datalab command "{}"'.format(' '.join(cmd)))
        return subprocess.check_output(cmd)

    def test_create_delete(self):
        instance_name = ""
        with DatalabInstance(self.test_run_name,
                             self.project,
                             self.zone) as instance:
            instance_name = instance.name
            self.assertIn('RUNNING', instance.status())
        instances = self.call_datalab('list', [])
        self.assertNotIn(instance_name, instances)

    def test_connect(self):
        instance_name = ""
        with DatalabInstance(self.test_run_name,
                             self.project,
                             self.zone) as instance:
            instance_name = instance.name
            self.assertIn('RUNNING', instance.status())
            self.call_datalab('stop', [instance.name])
            self.assertIn('TERMINATED', instance.status())
            with tempfile.NamedTemporaryFile() as tmp:
                with DatalabConnection(self.project, self.zone,
                                       instance.name, tmp):
                    readme = urllib2.urlopen(readme_url)
                    readme_contents = readme.read()
                    print('README contents returned: "{}"'.format(
                        readme_contents))
                    self.assertIn(readme_header, readme_contents)

        instances = self.call_datalab('list', [])
        self.assertNotIn(instance_name, instances)


if __name__ == '__main__':
    unittest.main()
