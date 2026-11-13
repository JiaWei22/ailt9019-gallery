from django.db import models, transaction, router
class Event(models.Model):
    project_counter = models.PositiveIntegerField(default=0, editable=False)
    def save(self, *args, **kwargs):
        if not self._state.adding:
            # Only the atomic project allocator updates this counter.
            fields = kwargs.get('update_fields')
            kwargs['update_fields'] = [f.name for f in self._meta.concrete_fields if not f.primary_key and f.name != 'project_counter'] if fields is None else [f for f in fields if f != 'project_counter']
        return super().save(*args, **kwargs)

    title = models.CharField(max_length=120, default='W13 Showcase')
    deadline = models.DateTimeField()
    opened = models.BooleanField(default=False)
class Project(models.Model):
    number = models.PositiveIntegerField(editable=False)

    @property
    def code(self):
        # A01–A10, B11–B20 ...; works beyond Z without punctuation.
        block = (self.number - 1) // 10 + 1
        letters = ''
        while block:
            block, digit = divmod(block - 1, 26)
            letters = chr(65 + digit) + letters
        return f'{letters}{self.number:02d}'

    def save(self, *args, **kwargs):
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        if self._state.adding:
            if self.number is not None:
                raise ValueError('Project numbers are allocated automatically.')
            with transaction.atomic(using=using):
                # Write first: serializes allocation on SQLite and row-locking databases.
                Event.objects.using(using).filter(pk=self.event_id).update(project_counter=models.F('project_counter') + 1)
                self.number = Event.objects.using(using).get(pk=self.event_id).project_counter
                try:
                    return super().save(*args, **kwargs)
                except Exception:
                    self.number = None
                    raise
        original = type(self).objects.using(using).values('event_id', 'number').get(pk=self.pk)
        if self.event_id != original['event_id'] or self.number != original['number']:
            raise ValueError('A project’s event and number cannot be changed.')
        return super().save(*args, **kwargs)

    @property
    def material_warnings(self):
        details = getattr(self, 'projectdetails', None)
        warnings = []
        if not details or not details.repository_url: warnings.append('Missing repository link')
        for label, video, prefix in [('Presentation', self.video, 'presentation'), ('Demo', self.demo_video, 'demo')]:
            if not video: warnings.append('Missing ' + label + ' video')
            elif not details or getattr(details, prefix + '_status') == 'unchecked': warnings.append(label + ' video not checked')
            elif getattr(details, prefix + '_status') == 'problem': warnings.append(label + ' video has a playback problem')
        return warnings

    vote_reset_at = models.DateTimeField(null=True, blank=True)
    event = models.ForeignKey(Event,on_delete=models.PROTECT)
    team = models.ForeignKey('reviews.Team',on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField()
    short_description = models.CharField(max_length=500,blank=True)
    # Legacy video remains the presentation video; existing records are preserved.
    video = models.CharField(max_length=11,blank=True)
    demo_video = models.CharField(max_length=11,blank=True)
    published = models.BooleanField(default=False)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','team'],name='w13_project_team'),
                     models.UniqueConstraint(fields=['event','number'],name='w13_project_number')]
class Assignment(models.Model):
    active = models.BooleanField(default=True)
    reviewer = models.ForeignKey('reviews.ReviewerIdentity',on_delete=models.PROTECT)
    project = models.ForeignKey(Project,on_delete=models.PROTECT)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['reviewer','project'],name='w13_assignment')]
class Review(models.Model):
    assignment = models.OneToOneField(Assignment,on_delete=models.PROTECT)
    scores = models.JSONField()
    strength = models.TextField()
    improvement = models.TextField()
    submitted = models.DateTimeField(auto_now=True)
class Ballot(models.Model):
    event = models.ForeignKey(Event,on_delete=models.PROTECT)
    reviewer = models.ForeignKey('reviews.ReviewerIdentity',on_delete=models.PROTECT)
    choices = models.JSONField()
    submitted = models.DateTimeField(auto_now=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['event','reviewer'],name='w13_ballot')]
class Audit(models.Model):
    action = models.CharField(max_length=80)
    actor = models.CharField(max_length=80)
    details = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)

class EventConfig(models.Model):
    event = models.OneToOneField(Event, on_delete=models.PROTECT)
    review_start = models.DateTimeField(null=True, blank=True)
    review_end = models.DateTimeField(null=True, blank=True)
    vote_start = models.DateTimeField(null=True, blank=True)
    vote_end = models.DateTimeField(null=True, blank=True)
    allow_self_vote = models.BooleanField(default=True)
    allow_vote_edit = models.BooleanField(default=True)
    allow_review_edit = models.BooleanField(default=True)
    confirmed = models.BooleanField(default=False)
    contact = models.CharField(max_length=200, blank=True)
    content_frozen = models.BooleanField(default=False)
    participant_codes = models.JSONField(null=True,blank=True,default=None)
    closing_at = models.DateTimeField(null=True, blank=True)
    intra_team_deadline = models.DateTimeField(null=True, blank=True)
    intra_team_url = models.URLField(blank=True)
    closing_url = models.URLField(blank=True)
    agenda_url = models.URLField(blank=True)
    moodle_url = models.URLField(blank=True)
    submissions_enabled = models.BooleanField(default=False)
    submission_deadline = models.DateTimeField(null=True,blank=True)

class ProjectSubmission(models.Model):
    project = models.ForeignKey(Project,on_delete=models.PROTECT,related_name='submissions')
    author = models.ForeignKey('reviews.ReviewerIdentity',on_delete=models.PROTECT)
    request_key = models.UUIDField(unique=True)
    content = models.JSONField()
    submitted_at = models.DateTimeField(auto_now_add=True)

class ProjectDetails(models.Model):
    project = models.OneToOneField(Project, on_delete=models.PROTECT)
    project_url = models.URLField(blank=True)
    repository_url = models.URLField(blank=True)
    presentation_status = models.CharField(max_length=20, default='unchecked', choices=[('unchecked','Unchecked'),('playable','Playable'),('problem','Problem')])
    presentation_notes = models.TextField(blank=True)
    presentation_checked_at = models.DateTimeField(null=True, blank=True)
    demo_status = models.CharField(max_length=20, default='unchecked', choices=[('unchecked','Unchecked'),('playable','Playable'),('problem','Problem')])
    demo_notes = models.TextField(blank=True)
    demo_checked_at = models.DateTimeField(null=True, blank=True)
    # Retain historical combined checks; never infer individual playback from them.
    video_status = models.CharField(max_length=20, default='unchecked')
    video_notes = models.TextField(blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)

class StaffAccount(models.Model):
    username = models.CharField(max_length=80, unique=True)
    password_hash = models.CharField(max_length=128)
    enabled = models.BooleanField(default=True)

    def set_password(self, raw):
        from django.contrib.auth.hashers import make_password
        self.password_hash = make_password(raw, hasher='pbkdf2_sha256')

    def check_password(self, raw):
        from django.contrib.auth.hashers import check_password
        return check_password(raw, self.password_hash)

class LoginBucket(models.Model):
    key = models.CharField(max_length=64, unique=True)
    attempts = models.PositiveIntegerField(default=0)
    expires = models.DateTimeField()
