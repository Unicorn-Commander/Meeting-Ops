from __future__ import annotations

import uuid
import pytest


@pytest.fixture
def fixture(client):
    from tests.test_agent_actions import _seed_user_org, _seed_session, _login_headers
    from database.database import SessionLocal
    from database.models import ActionItem, Transcription
    from database.database import engine
    from database.models import Base
    Base.metadata.create_all(bind=engine)
    suffix = uuid.uuid4().hex[:10]
    org, user = _seed_user_org(slug='manual-'+suffix, username='manual-'+suffix)
    row = _seed_session(org_id=org.id, user_id=user.id, title='Old synthetic content')
    with SessionLocal() as db:
        db.add(Transcription(session_id=row.id, text='Old words', speaker='Old speaker'))
        db.add(ActionItem(session_id=row.id, organization_id=org.id, text='Old task',
            source='final_summary', status='todo', project_ops_link_state='local_only'))
        db.commit()
    headers = _login_headers(client, user.username, org_slug=org.slug)
    return client, org, user, row, headers


def path(row):
    return f'/api/simple/recording-sessions/{row.session_id}/manual-content'


def body(client, row, headers):
    response = client.get(path(row), headers=headers)
    assert response.status_code == 200, response.text
    return {'expected_revision':response.json()['revision'], 'title':'Rivergreen synthetic kickoff',
        'description':'Explicitly authored demo content; no audio.',
        'lines':[{'speaker':'Dana','text':'Review the synthetic website plan.'},{'speaker':'Ben','text':'Prepare the fictional checkout spec.'}],
        'summary':'Dana and Ben reviewed a synthetic plan.', 'decisions':['Prepare the spec.'],
        'topics':['Website'], 'actions':[{'text':'Draft the fictional spec','owner':'Ben','due_date':'2026-09-30'}]}


def test_full_route_consistency_and_exact_retry(fixture):
    client, org, user, row, headers = fixture
    request = body(client,row,headers)
    r = client.put(path(row), json=request, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()['status']=='replaced'
    download=client.get(f'/api/simple/recording-sessions/{row.session_id}/download/transcript',headers=headers)
    assert download.status_code==200 and 'no audio or verified timing' in download.text
    assert '[00:00' not in download.text and 'Dana' in download.text

    simple=client.get(f'/api/simple/recording-sessions/{row.session_id}/download/transcript/simple',headers=headers)
    assert simple.status_code==200 and 'no audio or verified timing' in simple.text
    timed=client.get(f'/api/recording-sessions/{row.session_id}/export?format=srt',headers=headers)
    assert timed.status_code==409

    replay=client.put(path(row),json=request,headers=headers)
    assert replay.status_code==200 and replay.json()['replayed'] is True, replay.text
    from database.database import SessionLocal
    from database.models import RecordingSession,Transcription,ActionItem
    from auth.models import AuditLog
    with SessionLocal() as db:
        current=db.get(RecordingSession,row.id)
        assert current.user_id==user.id and current.organization_id==org.id and current.session_id==row.session_id
        assert current.transcript==current.transcript_simple=='Dana: Review the synthetic website plan.\nBen: Prepare the fictional checkout spec.'
        assert current.final_summary['summary']==request['summary']
        assert current.processing_metadata['manual_content']['inference_performed'] is False
        assert current.source_type=='manual_content' and not current.audio_file
        assert current.duration==0 and current.started_at is None
        segments=db.query(Transcription).filter_by(session_id=row.id).all()
        assert len(segments)==2 and all(x.start_time is None and x.confidence is None for x in segments)
        actions=db.query(ActionItem).filter_by(session_id=row.id).all()
        assert len(actions)==1 and actions[0].text==request['actions'][0]['text']
        assert actions[0].source=='manual' and actions[0].raw_payload['content_source']=='manually_authored'
        audits=db.query(AuditLog).filter_by(action='manual_content_replace',resource_id=str(row.id)).all()
        assert len(audits)==1 and 'Old words' not in str(audits[0].details)
        assert audits[0].details['after_digest']==r.json()['revision']


@pytest.mark.parametrize('field,value', [('audio_file','/not-read.wav'),('processing_job_id','pending'),('external_source','stable'),('is_combined',True),('brigade_graph_node_id','external'),('participants',[{'name':'verified person'}])])
def test_unsafe_session_refused(fixture,field,value):
    client, _, _, row, headers=fixture
    request=body(client,row,headers)
    from database.database import SessionLocal
    from database.models import RecordingSession
    with SessionLocal() as db:
        current=db.get(RecordingSession,row.id);setattr(current,field,value);db.commit()
    assert client.get(path(row),headers=headers).status_code==409
    assert client.put(path(row),json=request,headers=headers).status_code==409


@pytest.mark.parametrize('field,value',[('source','manual'),('status','done'),('project_ops_task_id','existing-task'),('project_ops_link_state','proposed')])
def test_protected_action_refused(fixture,field,value):
    client, _, _, row, headers=fixture
    request=body(client,row,headers)
    from database.database import SessionLocal
    from database.models import ActionItem
    with SessionLocal() as db:
        item=db.query(ActionItem).filter_by(session_id=row.id).one();setattr(item,field,value);db.commit()
    assert client.get(path(row),headers=headers).status_code==409
    assert client.put(path(row),json=request,headers=headers).status_code==409


def test_child_edit_changes_revision(fixture):
    client, _, _, row, headers=fixture
    request=body(client,row,headers)
    from database.database import SessionLocal
    from database.models import ActionItem
    with SessionLocal() as db:
        item=db.query(ActionItem).filter_by(session_id=row.id).one();item.text='Concurrent edit';db.commit()
    response=client.put(path(row),json=request,headers=headers)
    assert response.status_code==409 and 'Content changed' in response.json()['detail']


def test_viewer_and_cross_org_denied(fixture):
    client, org, user, row, headers=fixture
    request=body(client,row,headers)
    from database.database import SessionLocal
    from auth.models import UserOrganization,User
    from tests.test_agent_actions import _seed_user_org,_seed_session
    foreign_org,foreign_user=_seed_user_org(slug='other-'+uuid.uuid4().hex[:8],username='other-'+uuid.uuid4().hex[:8])
    foreign=_seed_session(org_id=foreign_org.id,user_id=foreign_user.id)
    with SessionLocal() as db:
        db.query(UserOrganization).filter_by(user_id=user.id,organization_id=org.id).one().role='viewer';db.commit()
    assert client.get(path(row),headers=headers).status_code==403
    assert client.put(path(row),json=request,headers=headers).status_code==403
    with SessionLocal() as db:
        db.get(User,user.id).is_superuser=True;db.commit()
    assert client.put(path(foreign),json=request,headers=headers).status_code==404
    assert client.put(path(row),json=request).status_code in (401,403)


def test_failure_rolls_back_all_content(fixture,monkeypatch):
    client, _, _, row, headers=fixture
    request=body(client,row,headers)
    from services import manual_session_content as service
    original=service.revision;calls=0
    def fail_after_mutation(*args):
        nonlocal calls
        calls+=1
        if calls==2:raise RuntimeError('Injected failure after child replacements')
        return original(*args)
    monkeypatch.setattr(service,'revision',fail_after_mutation)
    with pytest.raises(RuntimeError):client.put(path(row),json=request,headers=headers)
    from database.database import SessionLocal
    from database.models import RecordingSession,Transcription,ActionItem
    with SessionLocal() as db:
        assert db.get(RecordingSession,row.id).title=='Old synthetic content'
        assert db.query(Transcription).filter_by(session_id=row.id).one().text=='Old words'
        assert db.query(ActionItem).filter_by(session_id=row.id).one().text=='Old task'


@pytest.mark.parametrize('change',[{'unexpected':'x'},{'lines':[]},{'lines':[{'speaker':'Dana','text':'','start':1}]},{'expected_revision':'bad'},{'actions':[{'text':'Task','due_date':'tomorrow'}]}])
def test_strict_input(fixture,change):
    client, _, _, row, headers=fixture
    request=body(client,row,headers);request.update(change)
    assert client.put(path(row),json=request,headers=headers).status_code==422


def test_existing_provenance_and_metadata_preserved(fixture):
    client, _, _, row, headers = fixture
    from database.database import SessionLocal
    from database.models import RecordingSession
    with SessionLocal() as db:
        current = db.get(RecordingSession, row.id)
        current.source_type = "upload"
        current.processing_metadata = {"retained_setting": "keep"}
        db.commit()
    assert client.get(path(row), headers=headers).json()["content_source"] == "upload"
    assert client.put(path(row), json=body(client,row,headers), headers=headers).status_code == 200
    with SessionLocal() as db:
        assert db.get(RecordingSession, row.id).processing_metadata["retained_setting"] == "keep"


def test_lock_timeout_fails_closed(fixture, monkeypatch):
    client, _, _, row, headers = fixture
    request = body(client,row,headers)
    from api import manual_session_content as api
    from sqlalchemy.exc import OperationalError
    class LockTimeout(Exception):
        pgcode = "55P03"
    def locked(db):
        raise OperationalError("LOCK TABLE", {}, LockTimeout())
    monkeypatch.setattr(api, "lock_transcription_writes", locked)
    response = client.put(path(row), json=request, headers=headers)
    assert response.status_code == 409
    assert body(client,row,headers)["expected_revision"] == request["expected_revision"]


def test_batch_export_manual_text_and_untimed_formats(fixture):
    client, _, _, row, headers = fixture
    assert client.put(path(row), json=body(client,row,headers), headers=headers).status_code == 200
    from database.database import SessionLocal
    from database.models import RecordingSession
    from api.batch_export import (ExportOptions, export_to_txt, export_to_json,
        export_to_markdown, export_to_srt, export_to_pdf, export_to_docx)
    from fastapi import HTTPException
    import json, io, zipfile
    options = ExportOptions(includeTranscript=True, includeTimestamps=True)
    with SessionLocal() as db:
        current = db.get(RecordingSession,row.id)
        txt=export_to_txt(current,options)
        assert 'Dana' in txt and 'no audio or verified timing' in txt and '00:00' not in txt
        data=json.loads(export_to_json(current,options))
        assert data['timing_verified'] is False and len(data['transcript'])==2
        assert 'start' not in data['transcript'][0]
        excluded = options.model_copy(update={'includeTranscript':False, 'includeSpeakers':False})
        assert 'Review the synthetic website plan.' not in export_to_txt(current,excluded)
        assert json.loads(export_to_json(current,excluded))['transcript']==[]
        anonymous = options.model_copy(update={'includeSpeakers':False})
        assert 'speaker' not in json.loads(export_to_json(current,anonymous))['transcript'][0]
        md=export_to_markdown(current,options)
        assert 'Review the synthetic website plan.' in md and '00:00' not in md
        with pytest.raises(HTTPException) as error: export_to_srt(current,options)
        assert error.value.status_code == 409
        pdf=export_to_pdf(current,options)
        assert pdf.startswith(b'%PDF')
        docx=export_to_docx(current,options)
        document=zipfile.ZipFile(io.BytesIO(docx)).read('word/document.xml').decode()
        assert 'Review the synthetic website plan.' in document and '00:00' not in document


def test_unauthorized_request_never_locks_table(fixture,monkeypatch):
    client, org, user, row, headers = fixture
    request=body(client,row,headers)
    from api import manual_session_content as api
    from database.database import SessionLocal
    from auth.models import UserOrganization
    def forbidden(db): raise AssertionError('Unauthorized request acquired table lock')
    monkeypatch.setattr(api,'lock_transcription_writes',forbidden)
    with SessionLocal() as db:
        db.query(UserOrganization).filter_by(user_id=user.id,organization_id=org.id).one().role='viewer'
        db.commit()
    assert client.put(path(row),json=request,headers=headers).status_code==403
    assert client.put('/api/simple/recording-sessions/missing/manual-content',json=request,headers=headers).status_code==404


def test_supported_semantic_restore_after_exact_manual_action_removal(fixture):
    client, _, _, row, headers = fixture
    request=body(client,row,headers)
    original={'title':'Old synthetic content','description':'Restored authored content; no recording or inferred timing.',
        'lines':[{'speaker':'Old speaker','text':'Old words'}], 'summary':'Original synthetic summary.',
        'decisions':[], 'topics':[], 'actions':[{'text':'Old task'}]}
    assert client.put(path(row),json=request,headers=headers).status_code==200
    visible=client.get(f'/api/simple/recording-sessions/{row.session_id}',headers=headers).json()
    assert len(visible['action_items'])==1
    action=visible['action_items'][0]
    assert action['source']=='manual' and action['status']=='todo'
    assert not action['project_ops_task_id'] and not action['project_ops_proposal_id']
    # Whole-conversion replacement is intentionally blocked while manual children exist.
    assert client.get(path(row),headers=headers).status_code==409
    assert client.delete(f"/api/action-items/{action['id']}",headers=headers).status_code==204
    state=client.get(path(row),headers=headers)
    assert state.status_code==200
    restored=client.put(path(row),json={**original,'expected_revision':state.json()['revision']},headers=headers)
    assert restored.status_code==200
    after=client.get(f'/api/simple/recording-sessions/{row.session_id}',headers=headers).json()
    assert after['transcript_simple']=='Old speaker: Old words'
    assert after['final_summary']['summary']==original['summary']
    assert len(after['action_items'])==1 and after['action_items'][0]['text']=='Old task'
    assert after['action_items'][0]['source']=='manual'
    assert after['metadata']['manual_content']['inference_performed'] is False


@pytest.mark.parametrize('labels', [['Old display name', 'Other label'], [' Lone label ']])
def test_legacy_string_labels_backed_up_and_invalidated(fixture,labels):
    client, _, _, row, headers = fixture
    from database.database import SessionLocal
    from database.models import RecordingSession
    with SessionLocal() as db:
        db.get(RecordingSession,row.id).participants=labels
        db.commit()
    state=client.get(path(row),headers=headers)
    assert state.status_code==200 and state.json()['legacy_participant_labels']==labels
    request=body(client,row,headers)
    assert client.put(path(row),json=request,headers=headers).status_code==200
    after=client.get(f'/api/simple/recording-sessions/{row.session_id}',headers=headers).json()
    assert after['participants']==[]
    with SessionLocal() as db:
        stored=db.get(RecordingSession,row.id)
        assert stored.participants==[]
        for label in labels:
            assert label not in str(stored.processing_metadata)
            assert label not in stored.transcript_simple
            assert label not in str(stored.final_summary)


@pytest.mark.parametrize('labels', [['legacy',{'id':'person-id','name':'Linked'}], [{'name':'Structured'}], ['x'*201], ['x']*101, [''], ['  '], 'legacy', [1]])
def test_structured_mixed_or_unbounded_labels_refused(fixture,labels):
    client, _, _, row, headers = fixture
    request=body(client,row,headers)
    from database.database import SessionLocal
    from database.models import RecordingSession
    with SessionLocal() as db:
        db.get(RecordingSession,row.id).participants=labels
        db.commit()
    assert client.get(path(row),headers=headers).status_code==409
    assert client.put(path(row),json=request,headers=headers).status_code==409
