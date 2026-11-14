

def test_upload_get_edit_delete(sample_pdfs, seeker) -> None:  # type: ignore[no-untyped-def]
    client = seeker
    pdf = sample_pdfs["uday_ml.pdf"].read_bytes()
    r = client.post("/resume/upload", files={"file": ("uday.pdf", pdf, "application/pdf")})
    assert r.status_code == 201, r.text
    body = r.json()
    cid = body["id"]
    names = {s["name"] for s in body["skills"]}
    assert {"Python", "Machine Learning", "OpenCV"} <= names
    assert [s["name"] for s in body["steps"]][0] == "extract_text"
    assert body["education_level"] == "bachelors"
    assert body["years_experience"] > 0
    assert "Uday" not in (body["masked_text"] or "")

    assert client.get(f"/resume/{cid}").status_code == 200

    r = client.put(f"/resume/{cid}/skills", json={"add": ["Kubernetes", "Quantum Basket Weaving"], "remove": ["opencv"]})
    assert r.status_code == 200
    names = {s["name"] for s in r.json()["skills"]}
    assert "Kubernetes" in names and "Quantum Basket Weaving" in names and "OpenCV" not in names

    r = client.put(f"/resume/{cid}/preferences", json={"target_role": "ML Engineer", "locations": ["Bengaluru"]})
    assert r.json()["preferences"]["target_role"] == "ML Engineer"

    assert client.delete(f"/resume/{cid}").status_code == 204
    assert client.get(f"/resume/{cid}").status_code == 404


def test_upload_rejects_non_pdf(seeker) -> None:  # type: ignore[no-untyped-def]
    client = seeker
    r = client.post("/resume/upload", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 422
