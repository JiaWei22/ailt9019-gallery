"""Signed optimistic revisions; compare only after acquiring the event write lock."""
import hashlib,json
from django.core import signing

class RevisionConflict(ValueError):
    pass

def state(record):
    if record is None:return None
    return hashlib.sha256(json.dumps({f.attname:str(getattr(record,f.attname)) for f in record._meta.fields},sort_keys=True).encode()).hexdigest()

def issue(kind,owner,resource,record):
    return signing.dumps({'kind':kind,'owner':owner,'resource':resource,'state':state(record)},salt='w13-student-revision')

def check(token,kind,owner,resource,record):
    try:
        saved=signing.loads(token,salt='w13-student-revision',max_age=43200)
        if saved!={'kind':kind,'owner':owner,'resource':resource,'state':state(record)}:
            raise signing.BadSignature()
    except signing.BadSignature:
        raise RevisionConflict('This page is outdated or expired. Nothing was saved. Your draft is kept below. Open the latest saved version in a new tab and compare before submitting again.')
