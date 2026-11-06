"""Le Procès and the case-page agents answer in the interface language, even though the facts they read are in French."""
from types import SimpleNamespace


class FakeClient:
    """First answer in the wrong language (French), then the corrected English rewrite."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw["messages"])
        text = self.answers.pop(0)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15, prompt_tokens_details=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))], usage=usage)


def test_language_detector():
    import courtroom
    fr = "• Score très élevé et carte nationale utilisée à l'étranger pour le client. Réquisition : fraude."
    en = "• Very high score and a national card used abroad for the customer. Charge: fraud."
    assert courtroom.wrong_language(fr, "en") and not courtroom.wrong_language(en, "en")
    assert courtroom.wrong_language(en, "fr") and not courtroom.wrong_language(fr, "fr")


def test_trial_rewrites_a_french_answer_in_english(monkeypatch):
    import copilot
    import courtroom
    fake = FakeClient(["• Le client a utilisé sa carte à l'étranger pour un montant de 57 TND dans la journée. Réquisition : fraude.",
                       '• The customer used the card abroad; the purchase is "conforme_aux_habitudes". Charge: fraud.'])
    monkeypatch.setattr(copilot, "_client", lambda: fake)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
    text, tok = courtroom._call("procureur", "en", "- get_transaction → {...}")
    assert len(fake.calls) == 2 and "entirely in English" in fake.calls[1][-1]["content"]
    assert "FACTS:" in fake.calls[0][1]["content"] and "No French words" in fake.calls[0][1]["content"]
    assert not courtroom.wrong_language(text, "en") and "conforme_aux_habitudes" not in text      # field name cleaned
    assert tok["total"] == 30


def test_no_retry_when_the_language_is_right(monkeypatch):
    import copilot
    import courtroom
    fake = FakeClient(["• Le client connaît ce commerçant et paie en journée avec sa puce. Plaidoirie : opération légitime."])
    monkeypatch.setattr(copilot, "_client", lambda: fake)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")
    courtroom._call("defense", "fr", "- facts")
    assert len(fake.calls) == 1
