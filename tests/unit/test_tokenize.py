from app.knowledge.tokenize import (
    TokenizeConfig,
    parse_word_list,
    tokenize_for_search,
)


def test_tokenize_strips_chinese_question_suffix():
    tokens = tokenize_for_search("镇守者呢")
    assert "镇守者" in tokens


def test_tokenize_keeps_multi_word_query():
    tokens = tokenize_for_search("统御者 是什么")
    assert "统御者" in tokens
    assert "是什么" not in tokens


def test_tokenize_troops_line():
    line = "12\t镇守者\t镇守者是鹰之神界针对重装兵种防御而开发的得意之作。"
    tokens = tokenize_for_search(line, apply_stop_words=False)
    assert "镇守者" in tokens


def test_custom_stop_words_extend_defaults():
    cfg = TokenizeConfig.from_kb_fields(stop_words_text="兵种")
    tokens = tokenize_for_search("兵种介绍", cfg)
    assert "兵种" not in tokens


def test_user_dict_injects_domain_terms():
    cfg = TokenizeConfig.from_kb_fields(user_dict_text="镇守者\n统御者")
    tokens = tokenize_for_search("介绍一下", cfg)
    assert "镇守者" not in tokens
    tokens2 = tokenize_for_search("镇守者呢", cfg)
    assert "镇守者" in tokens2


def test_prioritize_vector_lexical_overlap():
    from app.knowledge.rag import RagService
    from app.knowledge.rerank import RankedChunk

    hits = [
        RankedChunk("d1", "kb1", 0, "国防军守城", "building", vector_score=0.9),
        RankedChunk("d2", "kb1", 0, "12 镇守者 重装防御", "troops", vector_score=0.5),
    ]
    ranked = RagService._prioritize_vector_lexical_overlap(
        "镇守者呢",
        hits,
        None,
        2,
    )
    assert ranked[0].document_id == "d2"


def test_parse_word_list():
    assert parse_word_list("a\nb, c; d") == frozenset({"a", "b", "c", "d"})

