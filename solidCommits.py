#!/usr/bin/env python3

import datetime
import os
import re
import sys

import json
import requests

from git import Repo, GitCommandError


def getPushUrl():
	origin = repo.remote('origin')
	urls = list(origin.urls)
	if len(urls) != 1:
		raise AssertionError(f'Expect 1 url for remote origin, but there are {len(urls)}.')
	originUrl = urls[0]
	assert originUrl.startswith('https://github.com')
	return pushUrl


def makeIssueBranch(branchName, commits):
	try:
		repo.create_head(branchName, 'master')
		repo.git.checkout(branchName, force=True)
		repo.git.cherry_pick(commits)

	except GitCommandError as e:
		raise AssertionError(f'Unable to rearrange commits {commits} based on master.\n{e}')

	repo.git.push(pushUrl, branchName)


def makePullRequest(token, repositoryId, branchName, title, body):
	body = '''
mutation
{
  createPullRequest(input:{
    	repositoryId:"%s",
    	baseRefName:"master",
    	headRefName:"%s",
    	title:"%s",
    	body:"%s"}) {
    pullRequest {
      createdAt
      id
    }
  }
}''' % (repositoryId, branchName, title, body)
	response = requests.post('https://api.github.com/graphql', headers={'Authorization': 'bearer ' + token}, data=json.dumps({"query": body}))
	data = response.json()

	if 'errors' in data:
		raise Exception(data['errors'])
	return data['data']['createPullRequest']['pullRequest']


def getRepositoryId(token, repositoryOwner, repositoryName):
	body = '''
{
  repository(name:"%s", owner:"%s") {
    id 
  }
}''' % (repositoryName, repositoryOwner)
	response = requests.post('https://api.github.com/graphql', headers={'Authorization': 'bearer ' + token}, data=json.dumps({"query": body}))
	data = response.json()
	return data['data']['repository']['id']


def getCommits(repo):
	# A commit is considered as stable if there are this number of commits after it.
	try:
		index = sys.argv.index("--mature-count")
		STABLE_COMMIT_COUNT = int(sys.argv[index + 1])
	except:
		STABLE_COMMIT_COUNT = 20
	try:
		index = sys.argv.index("--mature-age")
		STABLE_COMMIT_AGE = int(sys.argv[index + 1])
	except:
		STABLE_COMMIT_AGE = 1
	commits = list(repo.iter_commits('master..dev'))
	if len(commits) < STABLE_COMMIT_COUNT:
		print('No stable commits. mature count=' + str(STABLE_COMMIT_COUNT))
		exit(0)
	commits.reverse()
	stableCommits = [c for c in commits[:-STABLE_COMMIT_COUNT] if (datetime.datetime.now(c.committed_datetime.tzinfo) - c.committed_datetime).days >= STABLE_COMMIT_AGE]
	unstableCommits = [c for c in commits if c not in stableCommits]
	return stableCommits, unstableCommits


def getIssueId(commit):
	issueIdMatch = re.search(r'Issue: #(\d+)', commit.message)
	if issueIdMatch is not None:
		return int(issueIdMatch.group(1))
	else:
		return None


if __name__ == "__main__":
	if '--help' in sys.argv or len(sys.argv) == 0:
		print(f'''
	{"python " if sys.platform == 'win32' else "./" + os.path.basename(__file__)} [repo-path] 
--help\tShow this help.
--token str\tGitHub token.
--repositoryName str
--repositoryOwner str
--mature-count int\tA commit matures if there are int commits after it. Default value is 20.
--mature-age int\tA commit matures if its commit date is int days ago. Default value is 1.

The default value of repo-path is the current directory. 
''')

	repo = None
	try:
		if os.path.exists(sys.argv[-1]):
			repo = Repo(sys.argv[-1])
		else:
			repo = Repo(os.curdir)
	except Exception as e:
		print(sys.argv[-1] + " is not a valid Git repo. Append the proper path as the last parameter or `cd` to the target directory:\n" + str(e))
		exit(1)

	try:
		index = sys.argv.index("--token")
		GITHUB_TOKEN = sys.argv[index + 1]
	except:
		raise AssertionError('GitHub token is not found. Use --token option to provide it.')

	try:
		index = sys.argv.index('--repositoryName')
		repositoryName = sys.argv[index + 1]

		index = sys.argv.index('--repositoryOwner')
		repositoryOwner = sys.argv[index + 1]
	except:
		origin = repo.remote('origin')
		urls = list(origin.urls)
		if len(urls) != 1:
			raise AssertionError(f'Expect 1 url for remote origin, but there are {len(urls)}.')
		originUrl = urls[0]

		m = re.search(r'github\.com/([^/]+)/(.+?)\.git', originUrl)
		if m is None:
			raise AssertionError('Unable to find repository name and repository owner from git remote origin. You may want to provide it through command line options --repositoryName, --repositoryOwner.')

		repositoryOwner = m.group(1)
		repositoryName = m.group(2)

	repositoryId = getRepositoryId(GITHUB_TOKEN, repositoryOwner, repositoryName)

	stableCommits, unstableCommits = getCommits(repo)
	if len(stableCommits) == 0:
		print('No stable commits. Adjust --mature-count, --mature-age if you want.')
		exit()

	if repo.is_dirty():
		raise AssertionError('Unable to work on a dirty repository.')

	repo.git.checkout('master')
	hasError = False
	stableIssues = {}

	successfulCherryPicks = 0

	for commit in stableCommits:
		issueId = getIssueId(commit)
		if issueId is not None:
			print(commit.hexsha + ' is part of Issue ' + str(issueId))
			if issueId in stableIssues:
				stableIssues[issueId].append(commit.hexsha)
			else:
				stableIssues[issueId] = [commit.hexsha]
		else:
			print(commit.hexsha + ' is standalone commit.')

			try:
				# cherry pick standalone commits.
				repo.git.cherry_pick(commit.hexsha)
				successfulCherryPicks += 1
			except GitCommandError as e:
				print(f'Commit {commit.hexsha} is stable, but cannot be applied to master.', file=sys.stderr)
				hasError = True

	pushUrl = f"https://{GITHUB_TOKEN}@github.com/{repositoryOwner}/{repositoryName}.git"
	print(f'master branch has cherry-picked {successfulCherryPicks} commits.')
	if successfulCherryPicks > 0:
		repo.git.push(pushUrl, 'master')

	for commit in unstableCommits:
		issueIdMatch = re.search(r'Issue: #(\d+)', commit.message)
		if issueIdMatch is not None:
			issueId = int(issueIdMatch.group(1))
			stableIssues.pop(issueId, None)

	for id, commits in stableIssues.items():
		print(f'Issue {id} (commits {commits}) is stable.')

		branchName = 'Issue' + str(id)
		try:
			makeIssueBranch(branchName, commits)
		except Exception as e:
			print(str(e), file=sys.stderr)
			hasError = True

		try:
			print(makePullRequest(GITHUB_TOKEN, repositoryId, branchName, 'Implement issue ' + str(id), "Issue #" + str(id)))
		except Exception as e:
			print(str(e), file=sys.stderr)
			hasError = True

	if hasError:
		exit(1)
