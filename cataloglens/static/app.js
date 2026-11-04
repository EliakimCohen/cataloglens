"use strict";
const $ = id => document.getElementById(id);
const money = new Intl.NumberFormat("en-US", {style:"currency", currency:"USD"});
const text = (tag, value, cls) => { const node=document.createElement(tag); node.textContent=value; if(cls) node.className=cls; return node; };
async function api(path) {
  const response=await fetch(path);
  const body=await response.json();
  if(!response.ok) throw new Error(body.error || "Request failed");
  return body;
}
function showError(error) { $("error").textContent=error.message; $("error").hidden=false; }
function trace(product) {
  const list=document.createElement("dl");
  for(const [label,value] of [["Product",product.title],["Description",product.description],["Merchant / SKU",`${product.merchant} / ${product.sku}`],["Price",`${money.format(product.price_cents/100)} · stored as ${product.price_cents} cents`],["Source record",`${product.source} · record ${product.source_row}`],["Category decision",`${product.category} · ${product.category_source}`],["Supporting text",product.evidence || "No keyword match; other is the fallback"]]) {
    list.append(text("dt",label),text("dd",value));
  }
  $("trace-content").replaceChildren(list); $("trace").showModal();
}
async function loadProducts() {
  const params=new URLSearchParams({q:$("query").value,category:$("category").value,max_price:$("max-price").value});
  const products=await api(`/api/products?${params}`);
  $("products").replaceChildren();
  $("result-count").textContent=`${products.length} OFFERS`;
  for(const product of products) {
    const row=document.createElement("tr");
    const name=document.createElement("td"); name.append(text("strong",product.title),text("small",`${product.sku} · ${product.source}:${product.source_row}`));
    const category=document.createElement("td"); category.append(text("span",product.category,"badge"));
    const action=document.createElement("td"); const button=text("button","Inspect ↗","trace-button"); button.addEventListener("click",()=>trace(product)); action.append(button);
    row.append(name,text("td",product.merchant),category,text("td",money.format(product.price_cents/100),"price"),action); $("products").append(row);
  }
  if(!products.length) { const row=document.createElement("tr");const cell=text("td","No matching offers. Try fewer keywords or a higher maximum price.");cell.colSpan=5;row.append(cell);$("products").append(row); }
}
function renderReport(report) {
  for(const key of ["received","accepted","rejected"]) $(key).textContent=report[key];
  $("feed-count").textContent=`Across ${report.sources.length} imported feeds`;
  $("snapshot").textContent=`Import ${String(report.id).padStart(3,"0")}`;
  $("snapshot-date").textContent=new Date(report.created_at).toLocaleString("en-US",{dateStyle:"medium",timeStyle:"short"});
  $("duplicates").textContent=`${report.duplicates} DUPLICATE COLLAPSED`;
  $("pending").textContent=`${report.pending_reviews} PENDING`;
  for(const source of report.sources) {const card=document.createElement("article");card.className="source-card";card.append(text("strong",source.file),text("small",`${source.rows} input records`),text("p","SHA-256 fingerprint","eyebrow"),text("code",source.sha256));$("sources").append(card);}
  for(const issue of report.issues) {const row=document.createElement("tr");row.append(text("td",issue.source),text("td",issue.source_row),text("td",issue.reason));$("issues").append(row);}
}
function renderEvaluation(evaluation) {
  $("accuracy").textContent=`${(evaluation.accuracy*100).toFixed(1)}%`;
  for(const outcome of evaluation.outcomes) {const row=document.createElement("tr");const badge=document.createElement("td");badge.append(text("span",outcome.correct?"Match":"Mismatch",`badge ${outcome.correct?"good":"bad"}`));row.append(text("td",outcome.id),text("td",outcome.title),text("td",outcome.expected),text("td",outcome.predicted),badge);$("outcomes").append(row);}
}
function renderReviews(items) {
  if(!items.length) {const box=document.createElement("div");box.className="empty";box.append(text("h3","No model suggestions yet"),text("p","The demo runs entirely offline. Add a Claude API key and model identifier to generate one bounded suggestion for a selected offer."),text("code","python -m cataloglens suggest 1 --allow-paid-api\npython -m cataloglens reviews\npython -m cataloglens review 1 approve"),text("p","Prices and descriptions are never generated. A literal evidence quote is checked before a suggestion reaches this queue."));$("review-items").append(box);return;}
  for(const item of items) {const card=document.createElement("article");card.className="review-card";card.append(text("strong",item.title),text("p",`${item.current_category} → ${item.category} · ${item.status}`),text("p",`Evidence: ${item.evidence || "(fallback category)"}`),text("small",`${item.model} · ${item.input_tokens + item.output_tokens} tokens · ${item.elapsed_ms} ms`));$("review-items").append(card);}
}
document.querySelectorAll(".tab").forEach(button=>button.addEventListener("click",()=>{
  document.querySelectorAll(".tab").forEach(tab=>{const active=tab===button;tab.classList.toggle("active",active);tab.setAttribute("aria-pressed",String(active));});
  document.querySelectorAll(".panel").forEach(panel=>panel.hidden=panel.id!==button.dataset.panel);
}));
$("filters").addEventListener("submit",async event=>{event.preventDefault();$("error").hidden=true;try{await loadProducts();}catch(error){showError(error);}});
$("close-trace").addEventListener("click",()=>$("trace").close());
Promise.all([api("/api/report"),api("/api/evaluation"),api("/api/reviews")]).then(async ([report,evaluation,reviews])=>{renderReport(report);renderEvaluation(evaluation);renderReviews(reviews);await loadProducts();}).catch(showError);
