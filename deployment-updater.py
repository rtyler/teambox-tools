#!/usr/bin/env python
"""
    Teambox deployment updater script

    Copyright (c) 2011, Apture,Inc.

    This script was originally developed at Apture, Inc. and follows some conventions
    we use internally such as:
        * Reference Teambox "tasks" by task_id in commits
        * Using a date-stamp tag after each deployment:
            `TAG=$(date "+%Y.%m.%d.%H.%M"); it tag -s $TAG;`

    This script will use the Teambox API to dig through commits from the **last tag** to HEAD
    and create a new conversation in a project linking all the tasks deployed



    Sample commit format:

            commit 1c0e47260e66b8dbfb10ad6578a5a5c0239442ea
            Author: Angelo DiNardi <angelo@example.com>
            Date:   Wed Feb 23 16:44:54 2011 -0800

                Some very informative subject line

                More interesting details down in the body of the commit

                tb #237095
                tb #237099

                Change-Id: I82a75a7aafc85673e9245428f38709dcd9c46d4b
                Reviewed-on: http://gerrit.example.com/1234
                Tested-by: Jenkins <jenkins@example.com>
                Reviewed-by: Somebody Else <other@example.com>

    When the script picks up on the referenced tasks above and digs up the projects and
    the task names to reference
"""

import base64
import pprint
import re
import subprocess
import time
import urllib
import urllib2

import simplejson

#### STUFF TO CONFIGURE
######################################################################
TEAMBOX_USER = 'YOUR_ROLE_ACCOUNT_HERE'
TEAMBOX_PASSWORD = 'YOUR_ROLE_ACCOUNT_PASSWORD'
TEAMBOX_API_BASE = 'https://api.teambox.com/api/1'
GENERAL_PROJECT_ID = -1 # ID of the project to post the conversation to
######################################################################


TASK_ID_REGEX = re.compile(r'(?i)\s+tb\s*#([0-9]+)')
DELIMITER = '------[teambox integration delimiter]------'


def output_from(command):
    if isinstance(command, basestring):
        command = command.split(' ')
    p = subprocess.Popen(command, stdout=subprocess.PIPE)
    out, err = p.communicate()
    p.wait()
    return out, err


def make_api_request(command, data=None):
    url = '/'.join((TEAMBOX_API_BASE, command,))
    print ('Making API request to', url)
    request = urllib2.Request(url)
    tokens = base64.encodestring('%s:%s' % (TEAMBOX_USER, TEAMBOX_PASSWORD))
    request.add_header("Authorization", 'Basic %s' % tokens.replace('\n', ''))

    response = urllib2.urlopen(request, data)
    response = response.read()
    return simplejson.loads(response)

def main():
    tags, err = output_from('git tag -l')
    out = [tag for tag in tags.split('\n') if tag]
    last_tag = out[-1]
    print '>>> Previous tag: %s' % last_tag

    command = ['git', 'log', '--pretty=format:%%an: %%s (`%%h`)%%n%%n%%b%%n%s' % DELIMITER, '--reverse', '%s...' % last_tag]
    commits, err = output_from(command)
    commits = commits.split(DELIMITER)
    completed = []
    untasked = []
    for commit in commits:
        tasks = [int(t) for t in re.findall(TASK_ID_REGEX, commit)]
        if not tasks:
            subject = [c.strip() for c in commit.split('\n') if c]
            if subject:
                untasked.append(subject[0])
            continue
        completed.extend(tasks)

    users = make_api_request('users')
    users = users.get('objects', [])
    users = dict(((d['id'], d['username']) for d in users))

    projects = make_api_request('projects')
    projects = projects.get('objects', [])
    projects = dict(((d['id'], d['name']) for d in projects))

    task_data = {}
    for task_id in completed:
        try:
            data = make_api_request('tasks/%d' % task_id)
        except urllib2.HTTPError, ex:
            data = {'name' : 'Failed to access %s: %s' % task_id, 'project_id' : -1}
        task_data[task_id] = data

    text = u'*Achtung! We\'ve just deployed the following tasks!*\n\n'
    text += '#### Tasks\n\n'

    project_message = {}
    for task_id, data in task_data.iteritems():
        project_id = data['project_id']

        if not project_message.has_key(project_id):
            project_message[project_id] = []

        message = '   * [%(name)s](https://teambox.com/projects/%(project_id)s/tasks/%(id)s)' % data
        message += ' (filed by @%s)\n' % users.get(data['user_id'], 'Unknown')

        project_message[project_id].append(message)


    for project, message in project_message.iteritems():
        text += ' * **[%s](https://teambox.com/projects/%s)**\n' % (projects.get(project, 'Unknown'), project)
        text += '\n'.join(message)

    text += '\n\n#### Misc. Commits\n\n'
    for subject in untasked:
        text += ' * %s\n' % subject
    text += '\n\nGit tag: `%s`\n' % last_tag

    post = {'project_id' : GENERAL_PROJECT_ID,
            'body' : text,
            'name' : 'Deployment on %s' % time.strftime('%d %b %Y %H:%M', time.localtime()),
            }
    post = urllib.urlencode(post)
    make_api_request('conversations', post)

    return 0

if __name__ == '__main__':
    exit(main())

