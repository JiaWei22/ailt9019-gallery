from django.conf import settings
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone
from pathlib import Path

from .models import (
    CourseStaff,
    Proposal,
    Review,
    ReviewAssignment,
    ReviewerIdentity,
    Student,
    Team,
)
from .services import (
    assign_reviews,
    authenticate_student,
    check_staff_register,
    detect_anomalies,
    find_student_identity,
    generate_reviewer_code,
    get_or_create_proposal_event,
    is_hku_email,
    proposal_review_stats,
    store_otp,
    verify_otp,
)


def _event():
    return get_or_create_proposal_event()


def _team_student(team_name, student_id, name, email):
    event = _event()
    team, _ = Team.objects.get_or_create(name=team_name)
    Proposal.objects.get_or_create(
        event=event, team=team, defaults={"title": f"{team_name} paper"}
    )
    return Student.objects.create(
        student_id=student_id, name=name, email=email, team=team
    )


class AssignmentTests(TestCase):
    def test_reviewer_code_format(self):
        code = generate_reviewer_code()
        self.assertTrue(code.startswith("R-"))
        self.assertEqual(len(code), 6)

    def test_no_own_team_and_two_each(self):
        event = _event()
        teams = [Team.objects.create(name=f"T{i}") for i in range(4)]
        reviewers = []
        proposals = []
        for i, team in enumerate(teams):
            proposals.append(
                Proposal.objects.create(event=event, team=team, title=f"P{i}")
            )
            for j in range(3):
                student = Student.objects.create(
                    student_id=f"{i}{j}",
                    name=f"S{i}{j}",
                    email=f"s{i}{j}@hku.hk",
                    team=team,
                )
                reviewers.append(
                    ReviewerIdentity.objects.create(
                        student=student, code=generate_reviewer_code()
                    )
                )
        pairs = assign_reviews(reviewers, proposals, per_student=2)
        self.assertEqual(len(pairs), 24)
        for reviewer, proposal in pairs:
            self.assertNotEqual(reviewer.student.team_id, proposal.team_id)


class AuthTests(TestCase):
    def test_hku_email(self):
        self.assertTrue(is_hku_email("alex.chen@hku.hk"))
        self.assertTrue(is_hku_email("demo.reviewer@fixture.hku.hk"))
        self.assertFalse(is_hku_email("alex@gmail.com"))

    def test_otp_roundtrip(self):
        session = self.client.session
        code = store_otp(session, email="a@hku.hk", purpose="login", extra={"k": 1})
        session.save()
        self.assertEqual(len(code), 6)
        extra = verify_otp(session, email="a@hku.hk", purpose="login", code=code)
        self.assertEqual(extra, {"k": 1})
        self.assertIsNone(verify_otp(session, email="a@hku.hk", purpose="login", code=code))

    def test_password_login_rules(self):
        team = Team.objects.create(name="Team A")
        Proposal.objects.create(event=_event(), team=team, title="P")
        student = Student.objects.create(
            student_id="9000000001",
            name="Demo Reviewer",
            email="demo.reviewer@fixture.hku.hk",
            team=team,
        )
        student.set_login_password("Issued-OK")
        identity = ReviewerIdentity.objects.create(student=student, code="R-FAN1")

        found, err = authenticate_student("9000000001", "Issued-OK")
        self.assertEqual(found, identity)
        self.assertEqual(err, "")

        found, err = authenticate_student("R-FAN1", "Issued-OK")
        self.assertEqual(found, identity)

        found, err = authenticate_student("9000000001", "wrong")
        self.assertIsNone(found)
        self.assertIn("Wrong account or password", err)

        found, err = authenticate_student("999", "Issued-OK")
        self.assertIsNone(found)
        self.assertIn("Wrong account or password", err)

    def test_teacher_signup_needs_allowlist(self):
        CourseStaff.objects.create(uid="9000000003", name="Demo Reviewer")
        staff, err = check_staff_register("9000000003", "demo.reviewer@fixture.hku.hk")
        self.assertIsNotNone(staff)
        self.assertEqual(err, "")
        staff, err = check_staff_register("9000000001", "demo.reviewer@fixture.hku.hk")
        self.assertIsNone(staff)
        self.assertIn("course-staff list", err)

    def test_login_accepts_uid(self):
        student = _team_student("Team A", "9000000001", "Demo Reviewer", "demo.reviewer@fixture.hku.hk")
        identity = ReviewerIdentity.objects.create(
            student=student, code="R-FAN1", activated_at=timezone.now()
        )
        found, err = find_student_identity("9000000001")
        self.assertEqual(found, identity)
        self.assertEqual(err, "")

    def test_signup_redirects_to_login(self):
        response = self.client.get("/signup")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response["Location"])

    def test_student_login_hides_staff_entry(self):
        page = self.client.get("/login")
        self.assertContains(page, "Student login")
        self.assertNotContains(page, "Course staff")
        staff = self.client.get("/admin/login")
        self.assertContains(staff, "Course staff login")
        self.assertNotContains(staff, "Send email code")
        self.assertNotContains(staff, "Staff registration")
        gone = self.client.get("/django-admin/")
        self.assertEqual(gone.status_code, 404)

    def test_pdf_is_download_not_inline(self):
        student = _team_student("Team A", "A001", "Alex", "alex@hku.hk")
        other = _team_student("Team B", "B001", "Drew", "drew@hku.hk")
        identity = ReviewerIdentity.objects.create(student=student, code="R-AAA1")
        proposal = other.team.submissions.get()
        proposal.file.save("other.pdf", ContentFile(b"%PDF-1.4"), save=True)
        ReviewAssignment.objects.create(
            event=proposal.event, reviewer=identity, proposal=proposal
        )
        session = self.client.session
        session["reviewer_pk"] = identity.pk
        session.save()
        response = self.client.get(f"/forum/{proposal.pk}/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertNotIn("inline", response["Content-Disposition"])
        self.assertIn(proposal.download_name, response["Content-Disposition"])
        self.assertNotIn("Team", response["Content-Disposition"])
        self.assertNotIn("team", response["Content-Disposition"].lower())


class AnonymityTests(TestCase):
    def test_export_has_reviewer_id_not_student_name(self):
        team_a = Team.objects.create(name="Team A")
        team_b = Team.objects.create(name="Team B")
        student = Student.objects.create(
            student_id="Z999",
            name="Secret Name",
            email="secret.name@hku.hk",
            team=team_a,
        )
        reviewer = ReviewerIdentity.objects.create(student=student, code="R-TEST")
        proposal = Proposal.objects.create(
            event=_event(), team=team_b, title="Other Team Idea"
        )
        assignment = ReviewAssignment.objects.create(
            event=proposal.event, reviewer=reviewer, proposal=proposal
        )
        Review.objects.create(
            assignment=assignment,
            background=3,
            pipeline=8,
            evaluation=5,
            distribution=3,
            ethics=3,
            checkpoints=3,
            argumentation=3,
            presentation=3,
        )
        session = self.client.session
        session["is_course_staff"] = True
        session.save()
        response = self.client.get("/admin/export/")
        body = response.content.decode("utf-8")
        self.assertIn("R-TEST", body)
        self.assertNotIn("Secret Name", body)

    def test_incoming_reviews_hide_author_names(self):
        author = _team_student("Team A", "A001", "Alex Chen", "alex.chen@hku.hk")
        outsider = _team_student("Team B", "B001", "Secret Name", "secret.name@hku.hk")
        proposal = author.team.submissions.get()
        reviewer = ReviewerIdentity.objects.create(student=outsider, code="R-HIDE")
        owner = ReviewerIdentity.objects.create(student=author, code="R-OWN1")
        assignment = ReviewAssignment.objects.create(
            event=proposal.event, reviewer=reviewer, proposal=proposal
        )
        Review.objects.create(
            assignment=assignment,
            background=3,
            pipeline=8,
            evaluation=5,
            distribution=3,
            ethics=3,
            checkpoints=3,
            argumentation=3,
            presentation=3,
        )
        session = self.client.session
        session["reviewer_pk"] = owner.pk
        session.save()
        picker = self.client.get("/reviews/incoming")
        self.assertContains(picker, "Choose the event first")
        self.assertContains(picker, "W5 Proposal review")
        self.assertNotContains(picker, "Secret Name")
        response = self.client.get(f"/events/{proposal.event.slug}/feedback")
        self.assertContains(response, "R-HIDE")
        self.assertNotContains(response, "Secret Name")
        self.assertContains(response, "Feedback for your team proposal")


def _score_review(assignment, **fields):
    defaults = {
        "background": 4,
        "pipeline": 9,
        "evaluation": 6,
        "distribution": 4,
        "ethics": 4,
        "checkpoints": 3,
        "argumentation": 4,
        "presentation": 4,
    }
    defaults.update(fields)
    return Review.objects.create(assignment=assignment, **defaults)


class StaffStatsTests(TestCase):
    def setUp(self):
        self.author = _team_student("Team A", "A001", "Alex Chen", "alex.chen@hku.hk")
        self.proposal = self.author.team.submissions.get()
        self.outsiders = [
            _team_student("Team B", "B001", "Secret Name", "secret.name@hku.hk"),
            _team_student("Team C", "C001", "Hidden Person", "hidden.person@hku.hk"),
            _team_student("Team D", "D001", "Quiet Reviewer", "quiet.reviewer@hku.hk"),
            _team_student("Team E", "E001", "Low Marker", "low.marker@hku.hk"),
        ]
        self.codes = ["R-AAA1", "R-BBB2", "R-CCC3", "R-LOW4"]
        self.reviews = []
        for student, code in zip(self.outsiders, self.codes):
            reviewer = ReviewerIdentity.objects.create(student=student, code=code)
            assignment = ReviewAssignment.objects.create(
                event=self.proposal.event, reviewer=reviewer, proposal=self.proposal
            )
            if code == "R-LOW4":
                self.outlier = _score_review(
                    assignment,
                    background=1,
                    pipeline=2,
                    evaluation=1,
                    distribution=1,
                    ethics=1,
                    checkpoints=1,
                    argumentation=1,
                    presentation=1,
                )
                self.reviews.append(self.outlier)
            else:
                self.reviews.append(_score_review(assignment))

    def test_flags_score_far_from_median(self):
        flags = detect_anomalies(self.reviews)
        self.assertTrue(flags[self.outlier.pk])
        self.assertEqual(sum(flags.values()), 1)

    def test_exclude_drops_score_from_mean(self):
        before = proposal_review_stats(self.reviews)
        self.assertAlmostEqual(before["mean"], 30.75)
        self.outlier.counted = False
        self.outlier.save(update_fields=["counted"])
        after = proposal_review_stats(self.reviews)
        self.assertEqual(after["n_excluded"], 1)
        self.assertFalse(after["flagged"][self.outlier.pk])
        self.assertAlmostEqual(after["mean"], 38.0)
        self.assertGreater(after["mean"], before["mean"])

    def test_stats_pages_hide_student_names(self):
        session = self.client.session
        session["is_course_staff"] = True
        session.save()
        listing = self.client.get("/admin/stats/")
        self.assertContains(listing, "Team A")
        self.assertContains(listing, "Open")
        self.assertNotContains(listing, "Secret Name")
        self.assertNotContains(listing, "Low Marker")

        detail = self.client.get(f"/admin/stats/{self.author.team_id}")
        self.assertContains(detail, "R-LOW4")
        self.assertContains(detail, "yes")
        self.assertNotContains(detail, "Secret Name")
        self.assertNotContains(detail, "Low Marker")

    def test_staff_can_exclude_anomalous_score(self):
        session = self.client.session
        session["is_course_staff"] = True
        session.save()
        response = self.client.post(
            f"/admin/stats/{self.author.team_id}/reviews/{self.outlier.pk}/toggle"
        )
        self.assertEqual(response.status_code, 302)
        self.outlier.refresh_from_db()
        self.assertFalse(self.outlier.counted)
        listing = self.client.get("/admin/stats/")
        self.assertContains(listing, "1")

    def test_student_cannot_open_stats(self):
        owner = ReviewerIdentity.objects.create(student=self.author, code="R-OWN1")
        session = self.client.session
        session["reviewer_pk"] = owner.pk
        session.save()
        response = self.client.get("/admin/stats/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response["Location"])


class RosterImportTests(TestCase):
    def setUp(self):
        CourseStaff.objects.create(
            uid="9000000003",
            name="Demo Reviewer",
            email="demo.reviewer@fixture.hku.hk",
            registered=True,
        )

    def _import_sample(self, replace=True):
        from .roster import import_roster, parse_roster_file

        path = Path(__file__).resolve().parent.parent / "fixtures" / "students_test.csv"
        with path.open("rb") as handle:
            records = parse_roster_file(handle)
        return import_roster(records, replace=replace)

    def test_import_creates_andy_with_id_and_groups(self):
        from .roster import roster_rows

        self._import_sample()
        andy = Student.objects.get(student_id="9000000002")
        self.assertEqual(andy.name, "Andy")
        self.assertEqual(andy.email, "demo.reviewer@fixture.hku.hk")
        self.assertEqual(andy.team.name, "Group A")
        self.assertEqual(andy.identity.code, "R-AND1")
        self.assertFalse(andy.identity.is_activated)
        self.assertTrue(andy.check_login_password("AndyLab26"))
        self.assertEqual(andy.issued_password, "AndyLab26")
        groups = {
            assignment.proposal.team.name
            for assignment in andy.identity.assignments.select_related("proposal__team")
        }
        self.assertEqual(groups, {"Group B", "Group C"})
        rows = {row["student_id"]: row for row in roster_rows()}
        self.assertEqual(rows["9000000002"]["status"], "issued")
        self.assertEqual(rows["9000000002"]["assigned"], 2)

    def test_password_login_activates_andy(self):
        self._import_sample()
        bad = self.client.post(
            "/login",
            {"account": "9000000002", "password": "wrong"},
        )
        self.assertContains(bad, "Wrong account or password")
        self.assertFalse(Student.objects.get(student_id="9000000002").identity.is_activated)

        done = self.client.post(
            "/login",
            {"account": "R-AND1", "password": "AndyLab26"},
        )
        self.assertEqual(done.status_code, 302)
        self.assertTrue(done["Location"].endswith("/events"))
        andy = Student.objects.get(student_id="9000000002")
        self.assertTrue(andy.identity.is_activated)
        self.assertEqual(andy.identity.code, "R-AND1")
        self.assertIsNotNone(andy.identity.last_login_at)

    def test_staff_credentials_export_has_issued_password(self):
        self._import_sample()
        session = self.client.session
        session["is_course_staff"] = True
        session.save()
        response = self.client.get("/admin/credentials")
        body = response.content.decode("utf-8")
        self.assertIn("AndyLab26", body)
        self.assertIn("9000000002", body)
        self.assertIn("R-AND1", body)
        self.assertIn("groups_to_review", body)
        self.assertIn("Group B", body)
        self.assertIn("Group C", body)

        student = self.client.get("/login")
        self.assertNotContains(student, "AndyLab26")

    def test_staff_roster_updates_after_review(self):
        from .roster import roster_rows

        self._import_sample()
        from .services import activate_reviewer

        andy = Student.objects.get(student_id="9000000002")
        identity = activate_reviewer(andy)
        assignment = identity.assignments.select_related("proposal__team").order_by(
            "proposal__team__name"
        )[0]
        Review.objects.create(
            assignment=assignment,
            background=4,
            pipeline=9,
            evaluation=6,
            distribution=4,
            ethics=4,
            checkpoints=3,
            argumentation=4,
            presentation=4,
        )
        session = self.client.session
        session["is_course_staff"] = True
        session.save()
        page = self.client.get("/admin/")
        self.assertContains(page, "Andy")
        self.assertContains(page, "Logged in")
        self.assertContains(page, "1 / 2")
        row = next(r for r in roster_rows() if r["student_id"] == "9000000002")
        self.assertEqual(row["submitted"], 1)
        self.assertTrue(any(task["done"] for task in row["tasks"]))

    def test_staff_can_upload_csv(self):
        session = self.client.session
        session["is_course_staff"] = True
        session.save()
        path = Path(__file__).resolve().parent.parent / "fixtures" / "students_test.csv"
        with path.open("rb") as handle:
            response = self.client.post(
                "/admin/import",
                {"roster": handle, "replace": "on"},
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Student.objects.filter(student_id="9000000002").exists())
        board = self.client.get("/admin/")
        self.assertContains(board, "Andy")
        self.assertContains(board, "R-AND1")
        self.assertContains(board, "Never logged in")

    def test_student_events_page_lists_w5(self):
        self._import_sample()
        andy = Student.objects.get(student_id="9000000002")
        session = self.client.session
        session["reviewer_pk"] = andy.identity.pk
        session.save()
        listing = self.client.get("/events")
        self.assertContains(listing, "W5 Proposal review")
        detail = self.client.get("/events/w5-proposal")
        self.assertContains(detail, "assigned proposal")
        self.assertNotContains(detail, "Group B")
        self.assertNotContains(detail, "Group C")
        self.assertContains(detail, "Submission")

    def test_staff_events_page(self):
        self._import_sample()
        session = self.client.session
        session["is_course_staff"] = True
        session.save()
        page = self.client.get("/admin/events")
        self.assertContains(page, "W5 Proposal review")
        self.assertContains(page, "w5-proposal")


class RosterAccountTests(TestCase):
    def setUp(self):
        CourseStaff.objects.create(
            uid="9000000003",
            name="Demo Reviewer",
            email="demo.reviewer@fixture.hku.hk",
            registered=True,
        )

    def _staff(self):
        session = self.client.session
        session["is_course_staff"] = True
        session.save()

    def _import_sample(self):
        from .roster import import_roster, parse_roster_file

        path = Path(__file__).resolve().parent.parent / "fixtures" / "students_test.csv"
        with path.open("rb") as handle:
            records = parse_roster_file(handle)
        return import_roster(records, replace=True)

    def test_staff_can_add_one_student(self):
        from .roster import add_student

        result = add_student(
            name="Late Join",
            uid="9000000008",
            email="late@connect.hku.hk",
            group="D",
            password="LateJoin26",
        )
        student = Student.objects.get(student_id="9000000008")
        self.assertEqual(student.team.name, "Group D")
        self.assertEqual(result["reviewer_id"], student.identity.code)
        self.assertTrue(student.check_login_password("LateJoin26"))
        self.assertTrue(Proposal.objects.filter(team=student.team).exists())

        self._staff()
        page = self.client.post(
            "/admin/students/add",
            {
                "name": "Sam Lee",
                "uid": "9000000007",
                "email": "sam@connect.hku.hk",
                "group": "D",
                "password": "",
                "reviewer_id": "",
            },
        )
        self.assertEqual(page.status_code, 302)
        sam = Student.objects.get(student_id="9000000007")
        self.assertTrue(sam.issued_password)
        self.assertTrue(sam.identity.code.startswith("R-"))
        board = self.client.get("/admin/")
        self.assertContains(board, "Sam Lee")
        self.assertContains(board, "Add a late account")
        self.assertContains(board, "Set password")
        self.assertContains(board, sam.issued_password)

    def test_add_rejects_duplicate_uid(self):
        from .roster import RosterError, add_student

        add_student(
            name="First",
            uid="9000000004",
            email="first@connect.hku.hk",
            group="A",
        )
        with self.assertRaises(RosterError):
            add_student(
                name="Second",
                uid="9000000004",
                email="second@connect.hku.hk",
                group="A",
            )

    def test_change_group_keeps_existing_team_name(self):
        from .roster import add_student, change_student_group

        team = Team.objects.create(name="Team A")
        result = add_student(
            name="Pat",
            uid="9000000005",
            email="pat@connect.hku.hk",
            group="Team A",
        )
        student = result["student"]
        self.assertEqual(student.team_id, team.pk)
        moved = change_student_group(student, "Team A")
        self.assertFalse(moved["changed"])
        self.assertEqual(moved["new_group"], "Team A")

    def test_staff_can_change_group_and_drop_own_review(self):
        self._import_sample()
        andy = Student.objects.get(student_id="9000000002")
        assignment_ids = list(andy.identity.assignments.values_list("pk", flat=True))
        self.assertEqual(andy.identity.assignments.count(), 2)

        self._staff()
        response = self.client.post(
            f"/admin/students/{andy.pk}/group",
            {"group": "B"},
        )
        self.assertEqual(response.status_code, 302)
        andy.refresh_from_db()
        self.assertEqual(andy.team.name, "Group B")
        self.assertEqual(andy.identity.code, "R-AND1")
        remaining = {
            assignment.proposal.team.name
            for assignment in andy.identity.assignments.select_related("proposal__team")
        }
        self.assertEqual(remaining, {"Group C"})
        self.assertFalse(ReviewAssignment.objects.filter(pk__in=assignment_ids, proposal__team__name="Group B").exists())

    def test_staff_can_reset_password(self):
        self._import_sample()
        andy = Student.objects.get(student_id="9000000002")
        self._staff()
        response = self.client.post(
            f"/admin/students/{andy.pk}/password",
            {"password": "NewLab26"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"#student-{andy.pk}", response["Location"])
        andy.refresh_from_db()
        self.assertTrue(andy.check_login_password("NewLab26"))
        self.assertFalse(andy.check_login_password("AndyLab26"))
        self.assertEqual(andy.issued_password, "NewLab26")
        self.assertFalse(andy.identity.is_activated)

        generated = self.client.post(
            f"/admin/students/{andy.pk}/password",
            {"password": ""},
        )
        self.assertEqual(generated.status_code, 302)
        andy.refresh_from_db()
        self.assertTrue(andy.issued_password)
        self.assertNotEqual(andy.issued_password, "NewLab26")
        self.assertTrue(andy.check_login_password(andy.issued_password))

    def test_staff_can_delete_one_student(self):
        self._import_sample()
        andy = Student.objects.get(student_id="9000000002")
        team = andy.team
        proposal = Proposal.objects.get(team=team)
        assignment = andy.identity.assignments.first()
        Review.objects.create(
            assignment=assignment,
            background=4,
            pipeline=9,
            evaluation=6,
            distribution=4,
            ethics=4,
            checkpoints=3,
            argumentation=4,
            presentation=4,
        )
        self._staff()
        response = self.client.post(f"/admin/students/{andy.pk}/delete")
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Student.objects.filter(student_id="9000000002").exists())
        self.assertFalse(ReviewerIdentity.objects.filter(code="R-AND1").exists())
        self.assertFalse(Review.objects.exists())
        self.assertTrue(Team.objects.filter(pk=team.pk).exists())
        self.assertTrue(Proposal.objects.filter(pk=proposal.pk).exists())

    def test_student_cannot_manage_accounts(self):
        self._import_sample()
        andy = Student.objects.get(student_id="9000000002")
        session = self.client.session
        session["reviewer_pk"] = andy.identity.pk
        session.save()
        add = self.client.post(
            "/admin/students/add",
            {
                "name": "Nope",
                "uid": "9000000006",
                "email": "nope@connect.hku.hk",
                "group": "A",
            },
        )
        self.assertEqual(add.status_code, 302)
        self.assertIn("/admin/login", add["Location"])
        self.assertFalse(Student.objects.filter(student_id="9000000006").exists())
        delete = self.client.post(f"/admin/students/{andy.pk}/delete")
        self.assertEqual(delete.status_code, 302)
        self.assertIn("/admin/login", delete["Location"])
        self.assertTrue(Student.objects.filter(student_id="9000000002").exists())


class StaffOpsTests(TestCase):
    def setUp(self):
        CourseStaff.objects.create(
            uid="9000000003",
            name="Demo Reviewer",
            email="demo.reviewer@fixture.hku.hk",
            registered=True,
        )

    def _staff(self):
        session = self.client.session
        session["is_course_staff"] = True
        session.save()

    def test_assign_warns_before_replacing_tasks(self):
        from .roster import import_roster, parse_roster_file

        path = Path(__file__).resolve().parent.parent / "fixtures" / "students_test.csv"
        with path.open("rb") as handle:
            import_roster(parse_roster_file(handle), replace=True)
        andy = Student.objects.get(student_id="9000000002")
        self.assertEqual(andy.identity.assignments.count(), 2)
        self._staff()
        warned = self.client.post("/admin/assign-reviews", {"per_student": "1"})
        self.assertEqual(warned.status_code, 200)
        self.assertContains(warned, "Replace existing review tasks")
        self.assertEqual(andy.identity.assignments.count(), 2)
        replaced = self.client.post("/admin/assign-reviews/confirm", {"action": "replace"})
        self.assertEqual(replaced.status_code, 302)
        self.assertEqual(andy.identity.assignments.count(), 1)
        self.assertNotEqual(
            andy.identity.assignments.get().proposal.team_id,
            andy.team_id,
        )

    def test_staff_password_login(self):
        bad = self.client.post("/admin/login", {"password": "wrong"})
        self.assertContains(bad, "Wrong password")
        ok = self.client.post("/admin/login", {"password": settings.STAFF_PASSWORD})
        self.assertEqual(ok.status_code, 302)
        self.assertTrue(ok["Location"].endswith("/admin/"))

    def test_second_roster_import_is_rejected_while_locked(self):
        from reviews.views import _acquire_import_lock, _release_import_lock

        first = _acquire_import_lock()
        self.assertIsNotNone(first)
        second = _acquire_import_lock()
        self.assertIsNone(second)
        _release_import_lock(first)
        again = _acquire_import_lock()
        self.assertIsNotNone(again)
        _release_import_lock(again)

    def test_import_requires_reviewer_id_and_password(self):
        from .roster import RosterError, parse_roster_file

        raw = b"name,uid,group\nAndy,9000000002,A\n"
        with self.assertRaises(RosterError):
            parse_roster_file(ContentFile(raw, name="bare.csv"))
        missing_email = b"name,uid,email,group,reviewer_id,password\nAndy,9000000002,,A,R-AND1,AndyLab26\n"
        with self.assertRaises(RosterError) as caught:
            parse_roster_file(ContentFile(missing_email, name="no-email.csv"))
        self.assertIn("email", str(caught.exception))

    def test_import_asks_before_updating_existing_uid(self):
        from .roster import import_roster, parse_roster_file

        path = Path(__file__).resolve().parent.parent / "fixtures" / "students_test.csv"
        with path.open("rb") as handle:
            import_roster(parse_roster_file(handle), replace=True)
        self._staff()
        with path.open("rb") as handle:
            response = self.client.post("/admin/import", {"roster": handle})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already in the database")
        self.assertContains(response, "9000000002")
        skip = self.client.post("/admin/import/confirm", {"action": "skip"})
        self.assertEqual(skip.status_code, 302)
        self.assertEqual(Student.objects.filter(student_id="9000000002").count(), 1)

    def test_pdf_upload_reports_mismatch(self):
        from .roster import add_student
        from .pdf import write_simple_pdf
        import tempfile

        add_student(name="Pat", uid="9000000005", email="pat@connect.hku.hk", group="12")
        self._staff()
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "12.pdf"
            extra = Path(tmp) / "99.pdf"
            write_simple_pdf(good, "Group 12", ["demo"])
            write_simple_pdf(extra, "Group 99", ["extra"])
            with good.open("rb") as a, extra.open("rb") as b:
                response = self.client.post(
                    "/admin/pdfs",
                    {"pdfs": [a, b]},
                )
        self.assertEqual(response.status_code, 302)
        board = self.client.get("/admin/")
        self.assertContains(board, "99.pdf")
        self.assertTrue(
            Proposal.objects.filter(team__name="Group 12").exclude(file="").exists()
        )
        team = Team.objects.get(name="Group 12")
        pdf = self.client.get(f"/admin/stats/{team.pk}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        page = self.client.get(f"/admin/stats/{team.pk}")
        self.assertContains(page, "View PDF")
        board = self.client.get("/admin/")
        self.assertContains(board, "PDF ready")

    def test_staff_can_replace_one_group_pdf(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from .pdf import write_simple_pdf
        from .roster import add_student
        import tempfile

        add_student(name="Pat", uid="9000000005", email="pat@connect.hku.hk", group="12")
        self._staff()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.pdf"
            write_simple_pdf(path, "Replacement", ["Updated proposal"])
            data = path.read_bytes()
        team = Team.objects.get(name="Group 12")
        replaced = self.client.post(
            f"/admin/stats/{team.pk}/pdf/replace",
            {"pdf": SimpleUploadedFile("notes.pdf", data, content_type="application/pdf")},
        )
        self.assertEqual(replaced.status_code, 302)
        proposal = Proposal.objects.get(team=team)
        self.assertTrue(proposal.file)
        library = self.client.get("/admin/pdfs/library")
        self.assertContains(library, "Group 12")
        self.assertContains(library, proposal.download_name)
        self.assertContains(library, "PDF ready")
        rejected = self.client.post(
            f"/admin/stats/{team.pk}/pdf/replace",
            {"pdf": SimpleUploadedFile("99.pdf", data, content_type="application/pdf")},
        )
        self.assertEqual(rejected.status_code, 302)
        page = self.client.get(f"/admin/stats/{team.pk}")
        self.assertContains(page, "looks like group 99")

    def test_staff_can_see_outgoing_review(self):
        from .roster import import_roster, parse_roster_file

        path = Path(__file__).resolve().parent.parent / "fixtures" / "students_test.csv"
        with path.open("rb") as handle:
            import_roster(parse_roster_file(handle), replace=True)
        andy = Student.objects.get(student_id="9000000002")
        assignment = andy.identity.assignments.select_related("proposal__team").first()
        Review.objects.create(
            assignment=assignment,
            background=4,
            pipeline=9,
            evaluation=6,
            distribution=4,
            ethics=4,
            checkpoints=3,
            argumentation=4,
            presentation=4,
            suggestions="Please add a clearer evaluation plan.",
        )
        self._staff()
        page = self.client.get(f"/admin/students/{andy.pk}")
        self.assertContains(page, "Assigned review tasks")
        self.assertContains(page, "Submitted")
        self.assertContains(page, "Not submitted")
        self.assertContains(page, assignment.proposal.team.name)
        self.assertContains(page, "Please add a clearer evaluation plan.")
        self.assertContains(page, "are on the")
        self.assertNotContains(page, "Reviews of Group")
        team = self.client.get(f"/admin/stats/{assignment.proposal.team_id}")
        self.assertContains(team, "R-AND1")
        self.assertContains(team, "Incoming reviews for this group")

    def test_staff_lock_blocks_submit_and_edit(self):
        from .roster import import_roster, parse_roster_file
        from .services import get_or_create_proposal_event

        path = Path(__file__).resolve().parent.parent / "fixtures" / "students_test.csv"
        with path.open("rb") as handle:
            import_roster(parse_roster_file(handle), replace=True)
        andy = Student.objects.get(student_id="9000000002")
        assignment = andy.identity.assignments.first()
        event = get_or_create_proposal_event()
        self._staff()
        missing = self.client.post(
            f"/admin/events/{event.pk}/lock",
            {"action": "lock", "reason": ""},
        )
        self.assertEqual(missing.status_code, 302)
        event.refresh_from_db()
        self.assertTrue(event.is_open)

        locked = self.client.post(
            f"/admin/events/{event.pk}/lock",
            {"action": "lock", "reason": "the W5 deadline"},
        )
        self.assertEqual(locked.status_code, 302)
        event.refresh_from_db()
        self.assertFalse(event.is_open)
        self.assertEqual(event.lock_reason, "the W5 deadline")

        session = self.client.session
        session["reviewer_pk"] = andy.identity.pk
        session["is_course_staff"] = False
        session.save()
        page = self.client.get(f"/reviews/{assignment.pk}/edit")
        self.assertContains(page, "currently locked due to the W5 deadline.")
        self.assertNotContains(page, "Submit review")
        posted = self.client.post(
            f"/reviews/{assignment.pk}/edit",
            {"background": 1, "pipeline": 1, "evaluation": 1, "distribution": 1, "ethics": 1, "checkpoints": 1, "argumentation": 1, "presentation": 1, "suggestions": "too late to change this"},
        )
        self.assertEqual(posted.status_code, 302)
        self.assertFalse(Review.objects.filter(assignment=assignment).exists())

        Review.objects.create(
            assignment=assignment,
            background=4,
            pipeline=9,
            evaluation=6,
            distribution=4,
            ethics=4,
            checkpoints=3,
            argumentation=4,
            presentation=4,
            suggestions="Submitted before the lock.",
        )
        edit = self.client.post(f"/reviews/{assignment.pk}/request-edit")
        self.assertEqual(edit.status_code, 302)
        assignment.review.refresh_from_db()
        self.assertFalse(assignment.review.edit_allowed)
        shown = self.client.get(f"/reviews/{assignment.pk}/edit")
        self.assertContains(shown, "the W5 deadline")
        self.assertNotContains(shown, "Request an edit")

    def test_issue_credentials_from_raw_csv(self):
        from .credentials_issue import issue_credentials, parse_source_roster

        raw = b"student_number,name,group_name\n9000000009,\"EXAMPLE,Student\",1\n"
        records = parse_source_roster(ContentFile(raw, name="groups.csv"))
        rows = issue_credentials(records)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["uid"], "9000000009")
        self.assertEqual(rows[0]["group"], "Group 1")
        self.assertTrue(rows[0]["reviewer_id"].startswith("R-"))
        self.assertTrue(rows[0]["password"])
