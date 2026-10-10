from multi_agent.agents.report_template import render_quote_report


def test_keeps_the_quote_layout_and_escapes_values():
    html = render_quote_report({
        "quote_number": "42 <script>",
        "issued_at": "03/10/2026",
        "proposal_deadline": "",
        "requester": "Ana",
        "owner": "",
        "categories": [{"name": "Notebooks", "quantity": 67, "unit": "unidades"}],
        "items": [{
            "title": "Item 1 - Notebooks",
            "equipment_type": "Notebook",
            "brand": "",
            "model": "",
            "quantity": 67,
            "asset_number": "",
            "serial_number": "",
            "origin": "",
            "status": "",
            "description": "",
        }],
    })

    assert "Cotação de equipamentos" in html
    assert "Informações da cotação" in html
    assert "Overview de categorias selecionadas para descarte" in html
    assert "Informações dos conteúdos" in html
    assert "Notebooks: 67 unidades" in html
    assert "Tipo de equipamento: Notebook" in html
    assert "42 &lt;script&gt;" in html
    assert "<script>" not in html
    assert "zera.institutojf@gmail.com" in html


def test_drops_shapes_the_model_was_not_asked_for_and_caps_long_text():
    long_name = "Notebook " * 200
    html = render_quote_report({
        "quote_number": {"unexpected": True},
        "categories": [{"name": long_name, "quantity": ["muitas"], "unit": "unidades"}] * 3,
        "items": "não é uma lista",
        "report_html": "<script>alert(1)</script>",
    })

    assert "<script>" not in html
    assert "unexpected" not in html
    assert "Nenhum item informado." in html
    assert html.count("<li>") == 3
    assert "…" in html
    assert len(html) < 80_000


def test_renders_every_category_and_item():
    html = render_quote_report({
        "categories": [{"name": f"Cat {i}", "quantity": i, "unit": "unidades"} for i in range(120)],
        "items": [{"title": f"Item {i}", "equipment_type": "Notebook", "quantity": 1} for i in range(120)],
    })

    assert html.count("<li>") == 120
    assert html.count("Tipo de equipamento:") == 120


def test_renders_empty_sections_when_nothing_was_informed():
    html = render_quote_report({})

    assert "Nenhuma categoria informada." in html
    assert "Nenhum item informado." in html
    assert "Nenhum resumo informado." in html
    assert "Número de cotação:" in html


def test_renders_the_summary_as_paragraphs_and_points():
    html = render_quote_report({
        "summary": "Lote com 12 notebooks.\nUm deles está <danificado>.",
        "summary_points": ["12 notebooks", {"nope": True}, "Tela riscada"],
    })

    assert "Resumo" in html
    assert html.count("<section class=\"card summary\">") == 1
    assert "<p>Lote com 12 notebooks.</p>" in html
    assert "<p>Um deles está &lt;danificado&gt;.</p>" in html
    assert "<li>12 notebooks</li>" in html
    assert "<li>Tela riscada</li>" in html
    assert "nope" not in html
