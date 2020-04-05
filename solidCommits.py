import os
import re
import sys

from git import Repo, GitCommandError

# A commit is considered as stable if there are this number of commits after it.
STABLE_COMMIT_AGE = 10


def getPushUrl():
	origin = repo.remote('origin')
	urls = list(origin.urls)
	if len(urls) != 1:
		raise AssertionError(f'Expect 1 url for remote origin, but there are {len(urls)}.')
	originUrl = urls[0]
	assert originUrl.startswith('https://github.com')
	pushUrl = f"https://{GITHUB_TOKEN}@github.com{originUrl[len('https://github.com'):]}"
	return pushUrl


def makePullRequest(branchName, commits):
	try:
		repo.create_head(branchName, 'master')
		repo.git.checkout(branchName, force=True)
		repo.git.cherry_pick(commits)

	except GitCommandError as e:
		raise AssertionError(f'Unable to rearrange commits {commits} based on master.\n{e}')

	repo.git.push(pushUrl, branchName)


try:
	index = sys.argv.index("--token")
	GITHUB_TOKEN = sys.argv[index + 1]
except:
	raise AssertionError('GitHub token is not found. Use --token option to provide it.')

repo = Repo(os.path.dirname(os.path.abspath(__file__)) + '/../..')
commits = list(repo.iter_commits('master..dev'))
if len(commits) < STABLE_COMMIT_AGE:
	exit(0)

commits.reverse()
stableCommits = commits[:-STABLE_COMMIT_AGE]
unstableCommits = commits[-STABLE_COMMIT_AGE:]

repo.git.checkout('master')
if repo.is_dirty():
	raise AssertionError('Unable to work on a dirty repository.')

hasError = False
stableIssues = {}

pushUrl = getPushUrl()
for commit in stableCommits:
	issueIdMatch = re.search(r'Issue: #(\d+)', commit.message)
	if issueIdMatch is not None:
		issueId = int(issueIdMatch.group(1))
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
		except GitCommandError as e:
			print(f'Commit {commit.hexsha} is stable, but cannot be applied to master.', file=sys.stderr)
			hasError = True

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
		makePullRequest(branchName, commits)
	except Exception as e:
		print(str(e), file=sys.stderr)
		hasError = True
