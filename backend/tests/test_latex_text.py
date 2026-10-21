from app.utils.latex_text import delatex


def test_arxiv_author_names():
    assert delatex(r"Mustafa \"Ozayta\c{c}, \"Ozge Karada\u{g} Ata\c{c}") == "Mustafa Özaytaç, Özge Karadağ Ataç"
    assert (
        delatex(r"Fran\c cois, Jos\'e, M\"{u}ller, \v{S}ime, Ha\ss, {\O}stergaard")
        == "François, José, Müller, Šime, Haß, Østergaard"
    )


def test_plain_text_untouched():
    assert delatex("Alice Smith") == "Alice Smith"
    assert delatex(None) is None
    assert delatex("") == ""
