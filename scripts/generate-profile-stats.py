"""Render the three Leo cards from the profile owner's public GitHub data."""
import asyncio
import json
import os
from pathlib import Path
import re
import sys

import yaml

source = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(source))
os.chdir(source)

from src.core.github_client import GitHubClient
from src.core.graphql_queries import GraphQLQueries
from src.generators.base import GeneratorRegistry
from src.generators.overview import OverviewGenerator
from src.generators.languages import LanguagesGenerator
from src.generators.streak import StreakGenerator
from src.orchestrator import ImageOrchestrator

# The upstream queries use `viewer`, which identifies the Actions bot when
# using GITHUB_TOKEN. Keep the response alias but explicitly select the owner.
original_query = GitHubClient.query

async def owner_query(self, query):
    query = re.sub(r'\bviewer\s*\{',
                   'viewer: user(login: ' + json.dumps(self.username) + ') {', query)
    result = await original_query(self, query)
    if result.get('errors') or not result.get('data'):
        raise RuntimeError('GitHub returned incomplete statistics: ' + json.dumps(result.get('errors', [])))
    if 'viewer' in result['data'] and result['data']['viewer'] is None:
        raise RuntimeError('GitHub profile owner could not be loaded.')
    return result

def public_repositories(contrib_cursor=None, owned_cursor=None):
    cursor = json.dumps(owned_cursor)
    return """
    { viewer {
        login name followers { totalCount } following { totalCount }
        repositories(first: 25, privacy: PUBLIC, ownerAffiliations: OWNER,
                     after: CURSOR) {
            pageInfo { hasNextPage endCursor }
            nodes {
                nameWithOwner forkCount isFork isEmpty isArchived isPrivate
                stargazers { totalCount }
                languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
                    edges { size node { name color } }
                }
            }
        }
    } }
    """.replace('CURSOR', cursor)

GraphQLQueries.repos_overview = staticmethod(public_repositories)
GitHubClient.query = owner_query
GeneratorRegistry._generators = [OverviewGenerator, LanguagesGenerator, StreakGenerator]
config_path = source / 'config.yml'
config = yaml.safe_load(config_path.read_text())
config['github_user'] = os.environ['GITHUB_ACTOR']
config['timezone'] = 'America/Sao_Paulo'
config['themes']['enabled'] = ['light']
config['stats_generation'].update({
    'exclude_private_repos': 'true',
    'exclude_contrib_repos': 'true',
    'store_repo_views': 'false',
    'store_repo_clones': 'false',
    'show_views': 'false',
    'show_clones': 'false',
})
config_path.write_text(yaml.safe_dump(config, sort_keys=False))
asyncio.run(ImageOrchestrator.create_and_run())
