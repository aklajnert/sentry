from __future__ import absolute_import

from mock import patch

from base64 import b64encode
from datetime import datetime
from django.core.urlresolvers import reverse
from exam import fixture

from sentry.models import (
    Activity, ApiKey, ApiToken, CommitAuthor, CommitFileChange, Environment, Release, ReleaseCommit, ReleaseEnvironment, ReleaseProject, Repository
)
from sentry.plugins.providers.dummy.repository import DummyRepositoryProvider
from sentry.testutils import APITestCase, ReleaseCommitPatchTest


class OrganizationReleaseListTest(APITestCase):
    def test_simple(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.organization
        org2 = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team1 = self.create_team(organization=org)
        team2 = self.create_team(organization=org)

        project1 = self.create_project(teams=[team1], organization=org)
        project2 = self.create_project(teams=[team2], organization=org2)
        project3 = self.create_project(teams=[team1], organization=org)

        self.create_member(teams=[team1], user=user, organization=org)

        self.login_as(user=user)

        release1 = Release.objects.create(
            organization_id=org.id,
            version='1',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release1.add_project(project1)

        release2 = Release.objects.create(
            organization_id=org2.id,
            version='2',
            date_added=datetime(2013, 8, 14, 3, 8, 24, 880386),
        )
        release2.add_project(project2)

        release3 = Release.objects.create(
            organization_id=org.id,
            version='3',
            date_added=datetime(2013, 8, 12, 3, 8, 24, 880386),
            date_released=datetime(2013, 8, 15, 3, 8, 24, 880386),
        )
        release3.add_project(project3)

        release4 = Release.objects.create(
            organization_id=org.id,
            version='4',
            date_added=datetime(2013, 8, 14, 3, 8, 24, 880386),
        )
        release4.add_project(project3)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.get(url, format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 3
        assert response.data[0]['version'] == release3.version
        assert response.data[1]['version'] == release4.version
        assert response.data[2]['version'] == release1.version

    def test_query_filter(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.organization
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)

        project = self.create_project(teams=[team], organization=org)

        self.create_member(teams=[team], user=user, organization=org)

        self.login_as(user=user)

        release = Release.objects.create(
            organization_id=org.id,
            version='foobar',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release.add_project(project)

        release2 = Release.objects.create(
            organization_id=org.id,
            version='sdfsdfsdf',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release2.add_project(project)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.get(url + '?query=foo', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 1
        assert response.data[0]['version'] == release.version

        response = self.client.get(url + '?query=bar', format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 0

    def test_project_permissions(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team1 = self.create_team(organization=org)
        team2 = self.create_team(organization=org)

        project1 = self.create_project(teams=[team1], organization=org)
        project2 = self.create_project(teams=[team2], organization=org)

        self.create_member(teams=[team1], user=user, organization=org)
        self.login_as(user=user)

        release1 = Release.objects.create(
            organization_id=org.id,
            version='1',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release1.add_project(project1)

        release2 = Release.objects.create(
            organization_id=org.id,
            version='2',
            date_added=datetime(2013, 8, 14, 3, 8, 24, 880386),
        )
        release2.add_project(project2)

        release3 = Release.objects.create(
            organization_id=org.id,
            version='3',
            date_added=datetime(2013, 8, 12, 3, 8, 24, 880386),
            date_released=datetime(2013, 8, 15, 3, 8, 24, 880386),
        )
        release3.add_project(project1)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.get(url, format='json')

        assert response.status_code == 200, response.content
        assert len(response.data) == 2
        assert response.data[0]['version'] == release3.version
        assert response.data[1]['version'] == release1.version


class OrganizationReleaseCreateTest(APITestCase):
    def test_minimal(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])
        project2 = self.create_project(name='bar', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse(
            'sentry-api-0-organization-releases', kwargs={
                'organization_slug': org.slug,
            }
        )
        response = self.client.post(
            url, data={'version': '1.2.1',
                       'projects': [project.slug, project2.slug]}
        )

        assert response.status_code == 201, response.content
        assert response.data['version']

        release = Release.objects.get(
            version=response.data['version'],
        )
        assert not release.owner
        assert release.organization == org
        assert ReleaseProject.objects.filter(release=release, project=project).exists()
        assert ReleaseProject.objects.filter(release=release, project=project2).exists()

    def test_duplicate(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()
        repo = Repository.objects.create(
            provider='dummy',
            name='my-org/my-repository',
            organization_id=org.id,
        )

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        release = Release.objects.create(version='1.2.1', organization=org)

        url = reverse(
            'sentry-api-0-organization-releases', kwargs={
                'organization_slug': org.slug,
            }
        )

        with self.tasks():
            response = self.client.post(
                url,
                data={
                    'version':
                    '1.2.1',
                    'projects': [project.slug],
                    'refs': [
                        {
                            'repository': 'my-org/my-repository',
                            'commit': 'a' * 40,
                            'previousCommit': 'c' * 40,
                        }
                    ]
                }
            )

        release_commits1 = list(
            ReleaseCommit.objects.filter(
                release=release).order_by('order').values_list(
                'commit__key', flat=True)
        )

        # check that commits are overwritten
        assert release_commits1 == [
            u'62de626b7c7cfb8e77efb4273b1a3df4123e6216',
            u'58de626b7c7cfb8e77efb4273b1a3df4123e6345',
            u'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        ]

        # should be 201 because project was added
        assert response.status_code == 201, response.content

        with self.tasks():
            with patch.object(DummyRepositoryProvider, 'compare_commits') as mock_compare_commits:
                mock_compare_commits.return_value = [
                    {
                        'id': 'c' * 40,
                        'repository': repo.name,
                    }, {
                        'id': 'd' * 40,
                        'repository': repo.name,
                    }, {
                        'id': 'a' * 40,
                        'repository': repo.name,
                    }
                ]
                response2 = self.client.post(
                    url,
                    data={
                        'version':
                        '1.2.1',
                        'projects': [project.slug],
                        'refs': [
                            {
                                'repository': 'my-org/my-repository',
                                'commit': 'a' * 40,
                                'previousCommit': 'b' * 40,
                            }
                        ]
                    }
                )

        release_commits2 = list(
            ReleaseCommit.objects.filter(
                release=release).order_by('order').values_list(
                'commit__key', flat=True)
        )

        # check that commits are overwritten
        assert release_commits2 == [
            u'cccccccccccccccccccccccccccccccccccccccc',
            u'dddddddddddddddddddddddddddddddddddddddd',
            u'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        ]

        assert response2.status_code == 208, response.content
        assert Release.objects.filter(version='1.2.1', organization=org).count() == 1
        # make sure project was added
        assert ReleaseProject.objects.filter(release=release, project=project).exists()

    def test_activity(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])
        project2 = self.create_project(name='bar', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        release = Release.objects.create(
            version='1.2.1', date_released=datetime.utcnow(), organization=org
        )
        release.add_project(project)

        url = reverse(
            'sentry-api-0-organization-releases', kwargs={
                'organization_slug': org.slug,
            }
        )

        response = self.client.post(url, data={'version': '1.2.1', 'projects': [project.slug]})
        assert response.status_code == 208, response.content

        response = self.client.post(
            url, data={'version': '1.2.1',
                       'projects': [project.slug, project2.slug]}
        )

        # should be 201 because 1 project was added
        assert response.status_code == 201, response.content
        assert not Activity.objects.filter(
            type=Activity.RELEASE, project=project, ident=release.version
        ).exists()
        assert Activity.objects.filter(
            type=Activity.RELEASE, project=project2, ident=release.version
        ).exists()

    def test_activity_with_long_release(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])
        project2 = self.create_project(name='bar', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        release = Release.objects.create(
            version='x' * 65, date_released=datetime.utcnow(), organization=org
        )
        release.add_project(project)

        url = reverse(
            'sentry-api-0-organization-releases', kwargs={
                'organization_slug': org.slug,
            }
        )

        response = self.client.post(url, data={'version': 'x' * 65, 'projects': [project.slug]})
        assert response.status_code == 208, response.content

        response = self.client.post(
            url, data={'version': 'x' * 65,
                       'projects': [project.slug, project2.slug]}
        )

        # should be 201 because 1 project was added
        assert response.status_code == 201, response.content
        assert not Activity.objects.filter(
            type=Activity.RELEASE, project=project, ident=release.version[:64]
        ).exists()
        assert Activity.objects.filter(
            type=Activity.RELEASE, project=project2, ident=release.version[:64]
        ).exists()

    def test_version_whitespace(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})

        response = self.client.post(url, data={'version': '1.2.3\n', 'projects': [project.slug]})
        assert response.status_code == 400, response.content

        response = self.client.post(url, data={'version': '\n1.2.3', 'projects': [project.slug]})
        assert response.status_code == 400, response.content

        response = self.client.post(url, data={'version': '1.\n2.3', 'projects': [project.slug]})
        assert response.status_code == 400, response.content

        response = self.client.post(url, data={'version': '1.2.3\f', 'projects': [project.slug]})
        assert response.status_code == 400, response.content

        response = self.client.post(url, data={'version': '1.2.3\t', 'projects': [project.slug]})
        assert response.status_code == 400, response.content

        response = self.client.post(url, data={'version': '1.2.3+dev', 'projects': [project.slug]})
        assert response.status_code == 201, response.content
        assert response.data['version'] == '1.2.3+dev'

        release = Release.objects.get(
            organization_id=org.id,
            version=response.data['version'],
        )
        assert not release.owner

    def test_features(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.post(
            url, data={'version': '1.2.1',
                       'owner': self.user.email,
                       'projects': [project.slug]}
        )

        assert response.status_code == 201, response.content
        assert response.data['version']

        release = Release.objects.get(
            organization_id=org.id,
            version=response.data['version'],
        )
        assert release.owner == self.user

    def test_commits(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.post(
            url,
            data={
                'version': '1.2.1',
                'commits': [
                    {
                        'id': 'a' * 40
                    },
                    {
                        'id': 'b' * 40
                    },
                ],
                'projects': [project.slug]
            }
        )

        assert response.status_code == 201, (response.status_code, response.content)
        assert response.data['version']

        release = Release.objects.get(
            organization_id=org.id,
            version=response.data['version'],
        )

        rc_list = list(
            ReleaseCommit.objects.filter(
                release=release,
            ).select_related('commit', 'commit__author').order_by('order')
        )
        assert len(rc_list) == 2
        for rc in rc_list:
            assert rc.organization_id

    @patch('sentry.tasks.commits.fetch_commits')
    def test_commits_from_provider(self, mock_fetch_commits):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        repo = Repository.objects.create(
            organization_id=org.id,
            name='example/example',
            provider='dummy',
        )
        repo2 = Repository.objects.create(
            organization_id=org.id,
            name='example/example2',
            provider='dummy',
        )

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        self.client.post(
            url,
            data={
                'version':
                '1',
                'refs': [
                    {
                        'commit': '0' * 40,
                        'repository': repo.name
                    },
                    {
                        'commit': '0' * 40,
                        'repository': repo2.name
                    },
                ],
                'projects': [project.slug]
            }
        )
        response = self.client.post(
            url,
            data={
                'version':
                '1.2.1',
                'refs': [
                    {
                        'commit': 'a' * 40,
                        'repository': repo.name
                    },
                    {
                        'commit': 'b' * 40,
                        'repository': repo2.name
                    },
                ],
                'projects': [project.slug]
            }
        )
        assert response.status_code == 201

        mock_fetch_commits.apply_async.assert_called_with(
            kwargs={
                'release_id':
                Release.objects.get(version='1.2.1', organization=org).id,
                'user_id':
                user.id,
                'refs': [
                    {
                        'commit': 'a' * 40,
                        'repository': repo.name
                    },
                    {
                        'commit': 'b' * 40,
                        'repository': repo2.name
                    },
                ],
                'prev_release_id':
                Release.objects.get(version='1', organization=org).id,
            }
        )

    @patch('sentry.tasks.commits.fetch_commits')
    def test_commits_from_provider_deprecated_head_commits(self, mock_fetch_commits):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        repo = Repository.objects.create(
            organization_id=org.id,
            name='example/example',
            provider='dummy',
        )
        repo2 = Repository.objects.create(
            organization_id=org.id,
            name='example/example2',
            provider='dummy',
        )

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        self.client.post(
            url,
            data={
                'version':
                '1',
                'headCommits': [
                    {
                        'currentId': '0' * 40,
                        'repository': repo.name
                    },
                    {
                        'currentId': '0' * 40,
                        'repository': repo2.name
                    },
                ],
                'projects': [project.slug]
            }
        )
        response = self.client.post(
            url,
            data={
                'version':
                '1.2.1',
                'headCommits': [
                    {
                        'currentId': 'a' * 40,
                        'repository': repo.name
                    },
                    {
                        'currentId': 'b' * 40,
                        'repository': repo2.name
                    },
                ],
                'projects': [project.slug]
            }
        )

        mock_fetch_commits.apply_async.assert_called_with(
            kwargs={
                'release_id':
                Release.objects.get(version='1.2.1', organization=org).id,
                'user_id':
                user.id,
                'refs': [
                    {
                        'commit': 'a' * 40,
                        'repository': repo.name,
                        'previousCommit': None
                    },
                    {
                        'commit': 'b' * 40,
                        'repository': repo2.name,
                        'previousCommit': None
                    },
                ],
                'prev_release_id':
                Release.objects.get(version='1', organization=org).id,
            }
        )
        assert response.status_code == 201

    def test_bad_project_slug(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.post(
            url, data={'version': '1.2.1',
                       'projects': [project.slug, 'banana']}
        )
        assert response.status_code == 400
        assert 'Invalid project slugs' in response.content

    def test_project_permissions(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team1 = self.create_team(organization=org)
        team2 = self.create_team(organization=org)

        project1 = self.create_project(teams=[team1], organization=org)
        project2 = self.create_project(teams=[team2], organization=org)

        self.create_member(teams=[team1], user=user, organization=org)
        self.login_as(user=user)

        release1 = Release.objects.create(
            organization_id=org.id,
            version='1',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release1.add_project(project1)

        release2 = Release.objects.create(
            organization_id=org.id,
            version='2',
            date_added=datetime(2013, 8, 14, 3, 8, 24, 880386),
        )
        release2.add_project(project2)

        release3 = Release.objects.create(
            organization_id=org.id,
            version='3',
            date_added=datetime(2013, 8, 12, 3, 8, 24, 880386),
            date_released=datetime(2013, 8, 15, 3, 8, 24, 880386),
        )
        release3.add_project(project1)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.post(
            url, data={'version': '1.2.1',
                       'projects': [project1.slug, project2.slug]}
        )

        assert response.status_code == 400
        assert 'Invalid project slugs' in response.content

        response = self.client.post(url, data={'version': '1.2.1', 'projects': [project1.slug]})

        assert response.status_code == 201, response.content

    def test_api_key(self):
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        org2 = self.create_organization()

        team1 = self.create_team(organization=org)
        project1 = self.create_project(teams=[team1], organization=org)
        release1 = Release.objects.create(
            organization_id=org.id,
            version='1',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release1.add_project(project1)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})

        # test right org, wrong permissions level
        bad_api_key = ApiKey.objects.create(
            organization=org,
            scope_list=['project:read'],
        )
        response = self.client.post(
            url,
            data={'version': '1.2.1',
                  'projects': [project1.slug]},
            HTTP_AUTHORIZATION='Basic ' + b64encode(u'{}:'.format(bad_api_key.key))
        )
        assert response.status_code == 403

        # test wrong org, right permissions level
        wrong_org_api_key = ApiKey.objects.create(
            organization=org2,
            scope_list=['project:write'],
        )
        response = self.client.post(
            url,
            data={'version': '1.2.1',
                  'projects': [project1.slug]},
            HTTP_AUTHORIZATION='Basic ' + b64encode(u'{}:'.format(wrong_org_api_key.key))
        )
        assert response.status_code == 403

        # test right org, right permissions level
        good_api_key = ApiKey.objects.create(
            organization=org,
            scope_list=['project:write'],
        )
        response = self.client.post(
            url,
            data={'version': '1.2.1',
                  'projects': [project1.slug]},
            HTTP_AUTHORIZATION='Basic ' + b64encode(u'{}:'.format(good_api_key.key))
        )
        assert response.status_code == 201, response.content

    @patch('sentry.tasks.commits.fetch_commits')
    def test_api_token(self, mock_fetch_commits):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        repo = Repository.objects.create(
            organization_id=org.id,
            name='getsentry/sentry',
            provider='dummy',
        )
        repo2 = Repository.objects.create(
            organization_id=org.id,
            name='getsentry/sentry-plugins',
            provider='dummy',
        )

        api_token = ApiToken.objects.create(
            user=user,
            scope_list=['project:releases'],
        )

        team1 = self.create_team(organization=org)
        self.create_member(teams=[team1], user=user, organization=org)
        project1 = self.create_project(teams=[team1], organization=org)
        release1 = Release.objects.create(
            organization_id=org.id,
            version='1',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release1.add_project(project1)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})

        response = self.client.post(
            url,
            data={
                'version':
                '1.2.1',
                'refs': [
                    {
                        'commit': 'a' * 40,
                        'repository': repo.name,
                        'previousCommit': 'c' * 40
                    },
                    {
                        'commit': 'b' * 40,
                        'repository': repo2.name
                    },
                ],
                'projects': [project1.slug]
            },
            HTTP_AUTHORIZATION=u'Bearer {}'.format(api_token.token)
        )

        mock_fetch_commits.apply_async.assert_called_with(
            kwargs={
                'release_id':
                Release.objects.get(version='1.2.1', organization=org).id,
                'user_id':
                user.id,
                'refs': [
                    {
                        'commit': 'a' * 40,
                        'repository': repo.name,
                        'previousCommit': 'c' * 40
                    },
                    {
                        'commit': 'b' * 40,
                        'repository': repo2.name
                    },
                ],
                'prev_release_id':
                release1.id,
            }
        )

        assert response.status_code == 201

    def test_bad_repo_name(self):
        user = self.create_user(is_staff=False, is_superuser=False)
        org = self.create_organization()
        org.flags.allow_joinleave = False
        org.save()

        team = self.create_team(organization=org)
        project = self.create_project(name='foo', organization=org, teams=[team])

        self.create_member(teams=[team], user=user, organization=org)
        self.login_as(user=user)

        url = reverse('sentry-api-0-organization-releases', kwargs={'organization_slug': org.slug})
        response = self.client.post(
            url,
            data={
                'version': '1.2.1',
                'projects': [project.slug],
                'refs': [{
                    'repository': 'not_a_repo',
                    'commit': 'a' * 40,
                }]
            }
        )
        assert response.status_code == 400
        assert response.data == {'refs': [u'Invalid repository names: not_a_repo']}


class OrganizationReleaseListEnvironmentsTest(APITestCase):
    def setUp(self):
        self.login_as(user=self.user)
        org = self.create_organization(owner=self.user)
        team = self.create_team(organization=org)
        project1 = self.create_project(organization=org, teams=[team], name='foo')
        project2 = self.create_project(organization=org, teams=[team], name='bar')

        env1 = self.make_environment('prod', project1)
        env2 = self.make_environment('staging', project2)

        release1 = Release.objects.create(
            organization_id=org.id,
            version='1',
            date_added=datetime(2013, 8, 13, 3, 8, 24, 880386),
        )
        release1.add_project(project1)
        ReleaseEnvironment.objects.create(
            organization_id=org.id,
            project_id=project1.id,
            release_id=release1.id,
            environment_id=env1.id,
        )

        release2 = Release.objects.create(
            organization_id=org.id,
            version='2',
            date_added=datetime(2013, 8, 14, 3, 8, 24, 880386),
        )
        release2.add_project(project2)
        ReleaseEnvironment.objects.create(
            organization_id=org.id,
            project_id=project2.id,
            release_id=release2.id,
            environment_id=env2.id,
        )

        release3 = Release.objects.create(
            organization_id=org.id,
            version='3',
            date_added=datetime(2013, 8, 12, 3, 8, 24, 880386),
            date_released=datetime(2013, 8, 15, 3, 8, 24, 880386),
        )
        release3.add_project(project1)
        ReleaseEnvironment.objects.create(
            organization_id=org.id,
            project_id=project1.id,
            release_id=release3.id,
            environment_id=env2.id,
        )

        release4 = Release.objects.create(
            organization_id=org.id,
            version='4',
        )
        release4.add_project(project2)

        self.project1 = project1
        self.project2 = project2

        self.release1 = release1
        self.release2 = release2
        self.release3 = release3
        self.release4 = release4

        self.env1 = env1
        self.env2 = env2
        self.org = org

    def make_environment(self, name, project):
        env = Environment.objects.create(
            project_id=project.id,
            organization_id=project.organization_id,
            name=name,
        )
        env.add_project(project)
        return env

    def assert_releases(self, response, releases):
        assert response.status_code == 200, response.content
        assert len(response.data) == len(releases)

        response_versions = sorted([r['version'] for r in response.data])
        releases_versions = sorted([r.version for r in releases])
        assert response_versions == releases_versions

    def test_environments_filter(self):
        url = reverse(
            'sentry-api-0-organization-releases',
            kwargs={
                'organization_slug': self.org.slug,
            }
        )
        response = self.client.get(url + '?environment=' + self.env1.name, format='json')
        self.assert_releases(response, [self.release1])

        response = self.client.get(url + '?environment=' + self.env2.name, format='json')
        self.assert_releases(response, [self.release2, self.release3])

    def test_empty_environment(self):
        url = reverse(
            'sentry-api-0-organization-releases',
            kwargs={
                'organization_slug': self.org.slug,
            }
        )
        env = self.make_environment('', self.project2)
        ReleaseEnvironment.objects.create(
            organization_id=self.org.id,
            project_id=self.project2.id,
            release_id=self.release4.id,
            environment_id=env.id,
        )
        response = self.client.get(url + '?environment=', format='json')
        self.assert_releases(response, [self.release4])

    def test_all_environments(self):
        url = reverse(
            'sentry-api-0-organization-releases',
            kwargs={
                'organization_slug': self.org.slug,
            }
        )
        response = self.client.get(url, format='json')
        self.assert_releases(response, [self.release1, self.release2, self.release3, self.release4])

    def test_invalid_environment(self):
        url = reverse(
            'sentry-api-0-organization-releases',
            kwargs={
                'organization_slug': self.org.slug,
            }
        )
        response = self.client.get(url + '?environment=' + 'invalid_environment', format='json')
        self.assert_releases(response, [])


class OrganizationReleaseCreateCommitPatch(ReleaseCommitPatchTest):
    @fixture
    def url(self):
        return reverse(
            'sentry-api-0-organization-releases',
            kwargs={'organization_slug': self.org.slug}
        )

    def test_commits_with_patch_set(self):
        response = self.client.post(
            self.url,
            data={
                "version": "2d1ab93fe4bb42db80890f01f8358fc9f8fbff3b",
                "projects": [self.project.slug],
                "commits": [
                    {
                        "patch_set": [{"path": "hello.py", "type": "M"}, {"path": "templates/hola.html", "type": "D"}],
                        "repository": "laurynsentry/helloworld",
                        "author_email": "lauryndbrown@gmail.com",
                        "timestamp": "2018-11-29T18:50:28+03:00",
                        "author_name": "Lauryn Brown",
                        "message": "made changes to hello.",
                        "id": "2d1ab93fe4bb42db80890f01f8358fc9f8fbff3b"
                    }, {
                        "patch_set": [{"path": "templates/hello.html", "type": "M"}, {"path": "templates/goodbye.html", "type": "A"}],
                        "repository": "laurynsentry/helloworld",
                        "author_email": "lauryndbrown@gmail.com",
                        "timestamp": "2018-11-30T22:51:14+03:00",
                        "author_name": "Lauryn Brown",
                        "message": "Changed release",
                        "id": "be2fe070f6d1b8a572b67defc87af2582f9b0d78"
                    }
                ]
            }
        )

        assert response.status_code == 201, (response.status_code, response.content)
        assert response.data['version']

        release = Release.objects.get(
            organization_id=self.org.id,
            version=response.data['version'],
        )

        repo = Repository.objects.get(
            organization_id=self.org.id,
            name='laurynsentry/helloworld',
        )
        assert repo.provider is None

        rc_list = list(
            ReleaseCommit.objects.filter(
                release=release,
            ).select_related('commit', 'commit__author').order_by('order')
        )
        assert len(rc_list) == 2
        for rc in rc_list:
            assert rc.organization_id

        author = CommitAuthor.objects.get(
            organization_id=self.org.id,
            email='lauryndbrown@gmail.com'
        )
        assert author.name == 'Lauryn Brown'

        commits = [rc.commit for rc in rc_list]
        commits.sort(key=lambda c: c.date_added)

        self.assert_commit(
            commit=commits[0],
            repo_id=repo.id,
            key='2d1ab93fe4bb42db80890f01f8358fc9f8fbff3b',
            author_id=author.id,
            message='made changes to hello.',
        )

        self.assert_commit(
            commit=commits[1],
            repo_id=repo.id,
            key='be2fe070f6d1b8a572b67defc87af2582f9b0d78',
            author_id=author.id,
            message='Changed release',
        )

        file_changes = CommitFileChange.objects.filter(
            organization_id=self.org.id
        ).order_by('filename')

        self.assert_file_change(file_changes[0], 'M', 'hello.py', commits[0].id)
        self.assert_file_change(file_changes[1], 'A', 'templates/goodbye.html', commits[1].id)
        self.assert_file_change(file_changes[2], 'M', 'templates/hello.html', commits[1].id)
        self.assert_file_change(file_changes[3], 'D', 'templates/hola.html', commits[0].id)
