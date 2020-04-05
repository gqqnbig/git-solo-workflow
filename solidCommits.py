import os
import re
import sys

from git import Repo, GitCommandError

# A commit is considered as stable if there are this number of commits after it.
STABLE_COMMIT_AGE = 1

repo = Repo(os.path.dirname(os.path.abspath(__file__)) + '/../..')
commits = list(repo.iter_commits('master..dev'))
if len(commits) < STABLE_COMMIT_AGE:
	exit(0)

commits.reverse()
stableCommits = commits[:-STABLE_COMMIT_AGE]
unstableCommits = commits[-STABLE_COMMIT_AGE:]

repo.git.checkout('master')
if repo.is_dirty():
	print('Unable to work on dirty repository.', file=sys.stderr)
	exit(1)

hasError = False
stableIssues = {}
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

for commit in unstableCommits:
	issueIdMatch = re.search(r'Issue: #(\d+)', commit.message)
	if issueIdMatch is not None:
		issueId = int(issueIdMatch.group(1))
		stableIssues.pop(issueId, None)

for id, commits in stableIssues.items():
	print(f'Issue {id} (commits {commits}) is stable.')

	try:
		repo.create_head('Issue' + str(id), 'master')
		repo.git.checkout('Issue' + str(id), force=True)
		repo.git.cherry_pick(commits)
	except GitCommandError as e:
		print(f'Unable to rearrange commits {commits} based on master.\n{e}', file=sys.stderr)
		hasError = True
