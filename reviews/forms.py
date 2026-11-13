from django import forms

from .models import CRITERIA


class StudentLoginForm(forms.Form):
    account = forms.CharField(
        label="HKU UID or Reviewer ID",
        max_length=32,
        widget=forms.TextInput(
            attrs={"autocomplete": "username", "placeholder": "9000000002 or R-AND1"}
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={"autocomplete": "current-password", "placeholder": "Issued password"}
        ),
    )


class StaffUidForm(forms.Form):
    uid = forms.CharField(
        label="Staff UID",
        max_length=32,
        widget=forms.TextInput(attrs={"placeholder": "9000000003"}),
    )
    email = forms.EmailField(
        label="HKU email",
        required=False,
        widget=forms.EmailInput(attrs={"placeholder": "name@connect.hku.hk"}),
    )


class OtpForm(forms.Form):
    code = forms.CharField(
        label="Email code",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={"placeholder": "6-digit code", "inputmode": "numeric"}),
    )


class AddStudentForm(forms.Form):
    name = forms.CharField(label="Name", max_length=128)
    uid = forms.CharField(
        label="HKU UID",
        max_length=32,
        widget=forms.TextInput(attrs={"placeholder": "9000000002"}),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"placeholder": "name@connect.hku.hk"}),
    )
    group = forms.CharField(
        label="Group",
        max_length=32,
        widget=forms.TextInput(attrs={"placeholder": "A or Group 12", "list": "roster-groups"}),
    )
    password = forms.CharField(
        label="Password",
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={"placeholder": "Blank = generate"}),
    )
    reviewer_id = forms.CharField(
        label="Reviewer ID",
        required=False,
        max_length=16,
        widget=forms.TextInput(attrs={"placeholder": "Blank = issue one", "autocomplete": "off"}),
    )


class ChangeGroupForm(forms.Form):
    group = forms.CharField(
        label="Group",
        max_length=32,
        widget=forms.TextInput(attrs={"list": "roster-groups"}),
    )


class ChangePasswordForm(forms.Form):
    password = forms.CharField(
        label="Password",
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={"placeholder": "Blank = generate", "autocomplete": "off"}),
    )


class RosterImportForm(forms.Form):
    roster = forms.FileField(
        label="Student list",
        help_text="CSV or Excel. Required: name, uid, group, reviewer_id, password.",
    )
    replace = forms.BooleanField(
        required=False,
        label="Replace the current roster",
        help_text="Deletes current students, IDs, assignments, and reviews, then imports this file.",
    )


class PdfUploadForm(forms.Form):
    pdfs = forms.FileField(
        label="Group PDFs",
        help_text="One PDF per group, named 12.pdf or Group 12.pdf. A zip of those files is fine.",
    )


class StaffPasswordForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Staff password", "autofocus": True}),
    )


class ReviewForm(forms.Form):
    def __init__(self, *args, **kwargs):
        initial_review = kwargs.pop("initial_review", None)
        super().__init__(*args, **kwargs)
        for name, label, maximum, _part in CRITERIA:
            self.fields[name] = forms.IntegerField(
                label=label,
                min_value=0,
                max_value=maximum,
                widget=forms.NumberInput(
                    attrs={
                        "min": 0,
                        "max": maximum,
                        "step": 1,
                        "class": "score-input",
                        "data-part": _part.lower(),
                        "data-max": maximum,
                    }
                ),
            )
            self.fields[f"{name}_note"] = forms.CharField(
                label=f"{label} note",
                required=False,
                max_length=240,
                widget=forms.TextInput(
                    attrs={"placeholder": "Optional one-line note", "class": "note-input"}
                ),
            )
        self.fields["suggestions"] = forms.CharField(
            label="Overall suggestions",
            min_length=10,
            widget=forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "Longer comments for the team. Name one or two concrete changes.",
                    "class": "suggestions-input",
                }
            ),
        )
        if initial_review is not None:
            for name, _label, _maximum, _part in CRITERIA:
                self.fields[name].initial = getattr(initial_review, name)
                self.fields[f"{name}_note"].initial = getattr(initial_review, f"{name}_note")
            self.fields["suggestions"].initial = initial_review.suggestions

    def criterion_rows(self):
        rows = []
        last_part = None
        for name, label, maximum, part in CRITERIA:
            rows.append(
                {
                    "part": part,
                    "show_part": part != last_part,
                    "label": label,
                    "range": f"0–{maximum}",
                    "score": self[name],
                    "note": self[f"{name}_note"],
                }
            )
            last_part = part
        return rows
