"""Reset only the changed video's check; preserve the other video's evidence."""
def reset_changed_checks(details, old_videos, new_videos):
    for prefix, old, new in zip(('presentation', 'demo'), old_videos, new_videos):
        if old != new:
            setattr(details, prefix + '_status', 'unchecked')
            setattr(details, prefix + '_notes', '')
            setattr(details, prefix + '_checked_at', None)
    if old_videos != new_videos:
        details.video_status = 'unchecked'
        details.video_notes = ''
        details.checked_at = None
