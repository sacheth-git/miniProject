from app.privacy.pii_mask import guess_name, mask_pii

RESUME = """Ananya Kulkarni
ananya.k@example.com | +91 98450 12345 | linkedin.com/in/ananya-k
Gender: Female
Summary
She is a data engineer. Ms. Kulkarni led ETL work (Jan 2019 - 2021).
Education
B.Tech, National Institute of Technology Karnataka, Surathkal
MS Excel, Python
"""


def test_guess_name() -> None:
    assert guess_name(RESUME) == "Ananya Kulkarni"
    assert guess_name("RAVI KUMAR\nphone") == "RAVI KUMAR"
    assert "RAVI" not in mask_pii("RAVI KUMAR\nRavi built APIs").text
    assert guess_name("Curriculum Vitae\n") is None


def test_mask_pii_removes_identifiers() -> None:
    r = mask_pii(RESUME)
    t = r.text
    for leaked in ["Ananya", "Kulkarni", "example.com", "98450", "linkedin", "Female", "She ", "Ms.", "National Institute"]:
        assert leaked not in t, leaked
    assert "[NAME]" in t and "[EMAIL]" in t and "[PHONE]" in t and "[INSTITUTION]" in t
    assert r.counts["[EMAIL]"] == 1


def test_mask_keeps_skills_and_dates() -> None:
    t = mask_pii(RESUME).text
    assert "MS Excel" in t  # 'MS' is not a gender title here
    assert "Python" in t
    assert "Jan 2019 - 2021" in t  # year ranges are not phone numbers
    assert "data engineer" in t
