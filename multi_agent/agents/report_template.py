"""Fixed HTML for the equipment-quote PDF. The model never writes markup."""

from html import escape
from typing import Any

_FIELD_LIMIT = 400


def _text(value: Any, limit: int = _FIELD_LIMIT) -> str:
    """A scalar the model actually wrote, escaped and capped. Objects and lists are dropped."""
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return ""
    collapsed = " ".join(value.split())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "…"
    return escape(collapsed)


def _rows(items: Any) -> list[dict]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def render_quote_report(data: dict) -> str:
    """Renders the Zera cotação layout from structured fields."""

    categories = _rows(data.get("categories"))
    items = _rows(data.get("items"))

    if categories:
        category_html = "".join(
            f"<li>{_text(row.get('name'))}: {_text(row.get('quantity'))} {_text(row.get('unit') or 'unidades')}</li>"
            for row in categories
        )
    else:
        category_html = "<li>Nenhuma categoria informada.</li>"

    if items:
        item_html = "".join(_item_card(index, row) for index, row in enumerate(items, start=1))
    else:
        item_html = "<p class='empty'>Nenhum item informado.</p>"

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<title>Cotação de equipamentos</title>
<style>
  @page {{ size: A4; margin: 14mm 12mm 28mm 12mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: Helvetica, Arial, sans-serif; color: #111; font-size: 11px; }}
  h1, p, li, td {{ overflow-wrap: anywhere; word-break: break-word; }}
  .top {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
  .top td {{ vertical-align: middle; }}
  .brand {{ font-size: 26px; font-weight: 800; letter-spacing: 1px; width: 90px; }}
  .rule {{ width: 2px; background: #111; }}
  .title {{ padding-left: 12px; }}
  .title h1 {{ margin: 0; font-size: 18px; }}
  .title p {{ margin: 2px 0 0; color: #444; }}
  .card {{ border: 1.5px solid #111; border-radius: 14px; padding: 12px 14px 14px; margin-bottom: 12px; page-break-inside: avoid; }}
  .pill {{ display: inline-block; background: #111; color: #fff; border-radius: 8px; padding: 5px 10px; font-weight: 700; margin-bottom: 10px; }}
  .split {{ width: 100%; border-collapse: collapse; }}
  .split td {{ vertical-align: top; width: 50%; }}
  .split td + td {{ border-left: 1px solid #111; padding-left: 14px; }}
  .label {{ margin: 3px 0; }}
  ul {{ margin: 6px 0 0; padding-left: 18px; }}
  .item-title {{ font-weight: 700; margin: 0 0 6px; }}
  .empty {{ margin: 0; }}
  footer {{
    position: fixed; left: 0; right: 0; bottom: -18mm; height: 18mm;
    background: #111; color: #fff; padding: 8px 14px;
  }}
  footer table {{ width: 100%; border-collapse: collapse; }}
  footer td {{ color: #fff; vertical-align: middle; }}
  .slogan {{ font-weight: 800; letter-spacing: 0.4px; line-height: 1.25; width: 180px; }}
  .mail {{ text-align: right; }}
</style>
</head>
<body>
<table class="top">
  <tr>
    <td class="brand">ZERA</td>
    <td class="rule"></td>
    <td class="title">
      <h1>Cotação de equipamentos</h1>
      <p>Solicitação de coleta e destino</p>
    </td>
  </tr>
</table>

<section class="card">
  <div class="pill">Informações da cotação</div>
  <table class="split">
    <tr>
      <td>
        <p class="label">Número de cotação: {_text(data.get("quote_number"))}</p>
        <p class="label">Data de emissão: {_text(data.get("issued_at"))}</p>
        <p class="label">Prazo da proposta: {_text(data.get("proposal_deadline"))}</p>
      </td>
      <td>
        <p class="label">Solicitante: {_text(data.get("requester"))}</p>
        <p class="label">Responsável: {_text(data.get("owner"))}</p>
      </td>
    </tr>
  </table>
</section>

<section class="card">
  <div class="pill">Overview de categorias selecionadas para descarte</div>
  <p>Abaixo estão as categorias de equipamentos selecionadas para coleta e descarte.</p>
  <p>Os itens serão avaliados conforme as informações fornecidas.</p>
  <ul>{category_html}</ul>
</section>

<section class="card">
  <div class="pill">Informações dos conteúdos</div>
  {item_html}
</section>

<footer>
  <table>
    <tr>
      <td class="slogan">TRANSFORMANDO<br/>DESCARTE EM<br/>SOLUÇÃO</td>
      <td class="mail">zera.institutojf@gmail.com</td>
    </tr>
  </table>
</footer>
</body>
</html>
"""


def _item_card(index: int, row: dict) -> str:
    title = _text(row.get("title") or f"Item {index}")
    return f"""
  <table class="split">
    <tr>
      <td>
        <p class="item-title">{title}</p>
        <p class="label">Tipo de equipamento: {_text(row.get("equipment_type"))}</p>
        <p class="label">Marca: {_text(row.get("brand"))}</p>
        <p class="label">Modelo: {_text(row.get("model"))}</p>
        <p class="label">Quantidade: {_text(row.get("quantity"))}</p>
        <p class="label">Número patrimonial: {_text(row.get("asset_number"))}</p>
        <p class="label">Número de série: {_text(row.get("serial_number"))}</p>
      </td>
      <td>
        <p class="label">Unidade/Local de origem: {_text(row.get("origin"))}</p>
        <p class="label">Situação: {_text(row.get("status"))}</p>
        <p class="label">Descrição: {_text(row.get("description"))}</p>
      </td>
    </tr>
  </table>
"""
