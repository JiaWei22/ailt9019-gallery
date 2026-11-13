from django import forms
from .models import EventConfig, ProjectDetails
class EventForm(forms.ModelForm):
    revision=forms.CharField(widget=forms.HiddenInput)
    title = forms.CharField(max_length=120)
    opened = forms.BooleanField(required=False)
    participant_codes=forms.CharField(required=False,widget=forms.Textarea,
        help_text='Reviewer IDs separated by spaces or commas. Blank includes all existing identities; W5 roster is never modified.')
    def clean_participant_codes(self):
        import re
        from reviews.models import ReviewerIdentity
        text=self.cleaned_data['participant_codes'].strip()
        if not text:return None
        codes=re.split(r'[\s,]+',text)
        if len(set(codes))!=len(codes):raise forms.ValidationError('Duplicate Reviewer IDs.')
        known=set(ReviewerIdentity.objects.filter(code__in=codes).values_list('code',flat=True))
        missing=set(codes)-known
        if missing:raise forms.ValidationError('Unknown Reviewer IDs: '+', '.join(sorted(missing)))
        return sorted(codes)

    class Meta:
        model = EventConfig
        exclude = ['event', 'submissions_enabled', 'submission_deadline']
        widgets = {n: forms.DateTimeInput(format='%Y-%m-%dT%H:%M',attrs={'type':'datetime-local'}) for n in ['review_start','review_end','vote_start','vote_end','submission_deadline','closing_at','intra_team_deadline']}
    def clean(self):
        data=super().clean()
        for kind in ['review','vote']:
            if data.get(kind+'_start') and data.get(kind+'_end') and data[kind+'_start']>=data[kind+'_end']:
                self.add_error(kind+'_end','End must be after start.')
        for name in ['intra_team_url','closing_url','agenda_url','moodle_url']:
            value=data.get(name,'')
            if value and not value.startswith('https://'):
                self.add_error(name,'Use an HTTPS link, or leave blank until announced.')
        if data.get('opened'):
            for name in ['review_start','review_end','vote_start','vote_end']:
                if not data.get(name):self.add_error(name,'Set this time before opening reviews and voting.')
        if data.get('opened') and not data.get('confirmed'):
            self.add_error('confirmed','Confirm course rules before opening.')
        return data

class StudentProjectForm(forms.Form):
    revision=forms.CharField(widget=forms.HiddenInput)
    title=forms.CharField(max_length=200)
    short_description=forms.CharField(max_length=500,required=False,widget=forms.Textarea)
    description=forms.CharField(widget=forms.Textarea,help_text="Explain the user/problem, input–process–output, run steps, evidence and limitations. See the checklist above.")
    repository_url=forms.URLField(required=False, max_length=200, label='Repository URL', help_text='HTTPS code repository link. Give the course team access; the repository need not be public.')
    def clean_repository_url(self):
        value=self.cleaned_data['repository_url']
        if value and not value.startswith('https://'): raise forms.ValidationError('HTTPS required.')
        return value
    project_url=forms.URLField(required=False)
    youtube_url=forms.URLField(label="Presentation video",required=True,help_text='Upload to YouTube as Unlisted, allow embedding, and paste the watch or youtu.be link.')
    demo_youtube_url=forms.URLField(required=True,label="Demo video",help_text="YouTube Unlisted link showing the working system.")
    def clean_project_url(self):
        value=self.cleaned_data['project_url']
        if value and not value.startswith('https://'):raise forms.ValidationError('HTTPS required.')
        return value
    def clean_demo_youtube_url(self):
        from .views import video_id
        value=self.cleaned_data["demo_youtube_url"]
        if value:
            try: video_id(value)
            except ValueError as exc: raise forms.ValidationError(str(exc))
        return value
    def clean_youtube_url(self):
        from .views import video_id
        value=self.cleaned_data['youtube_url']
        try:video_id(value)
        except ValueError as exc:raise forms.ValidationError(str(exc))
        return value
class ProjectForm(forms.ModelForm):
    revision=forms.CharField(widget=forms.HiddenInput)
    title=forms.CharField(max_length=200)
    description=forms.CharField(widget=forms.Textarea)
    short_description=forms.CharField(max_length=500,required=False,widget=forms.Textarea)
    demo_youtube_url=forms.URLField(required=False,label="Demo video")
    youtube_url=forms.URLField(required=False,label="Presentation video")
    class Meta:
        model=ProjectDetails
        exclude=['project','checked_at','video_status','video_notes','presentation_checked_at','demo_checked_at']
        widgets={'video_status':forms.Select(choices=[('unchecked','Unchecked'),('playable','Playable'),('problem','Problem')])}
    def clean_demo_youtube_url(self):
        from .views import video_id
        value=self.cleaned_data["demo_youtube_url"]
        if value:
            try: video_id(value)
            except ValueError as exc: raise forms.ValidationError(str(exc))
        return value
    def clean_youtube_url(self):
        from .views import video_id
        url=self.cleaned_data['youtube_url']
        if url:
            try:video_id(url)
            except ValueError as e:raise forms.ValidationError(str(e))
        return url
    def clean_project_url(self):
        value=self.cleaned_data['project_url']
        if value and not value.startswith('https://'):raise forms.ValidationError('HTTPS required.')
        return value
    clean_repository_url = StudentProjectForm.clean_repository_url
    def clean(self):
        data = super().clean()
        for prefix, video_field in [('presentation','youtube_url'), ('demo','demo_youtube_url')]:
            if not data.get(video_field) and data.get(prefix + '_status') in ('playable','problem'):
                self.add_error(prefix + '_status', 'Add this video link before recording a check.')
        return data
    def clean_video_status(self):
        value=self.cleaned_data['video_status']
        if value not in ['unchecked','playable','problem']:raise forms.ValidationError('Invalid status.')
        return value
