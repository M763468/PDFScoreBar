"use strict";

const copy = {
  en: {
    submitTitle: "Number a PDF", file: "Score PDF", pages: "Pages (optional)",
    pagesHelp: "Separate page numbers with commas. Leave blank for all pages.",
    start: "Start numbering", jobsTitle: "Jobs", empty: "No submitted jobs.",
    uploading: "Uploading PDF…", submitted: "Job submitted", queued: "Queued",
    running: "Processing", succeeded: "Numbered PDF ready · Review available",
    review_required: "Numbered PDF ready · Review required", failed: "Failed",
    interrupted: "Interrupted · Select the PDF again to submit a new job",
    open: "Open numbered PDF", download: "Download", review: "Open correction GUI",
    listError: "Could not load jobs. Reconnecting…",
    requestError: "Could not submit the job", fileError: "Choose a non-empty PDF within 256 MiB",
    pagesError: "Enter positive page numbers separated by commas", busy: "Wait for a job to finish",
    page: "Page",
    stages: {
      job: "Starting job", input_validation: "Checking input", pdf_render: "Rendering PDF",
      score_detection: "Detecting score features", measure_construction: "Building measures",
      measure_number_recognition: "Reading measure counts", correction_application: "Applying corrections",
      numbering: "Assigning measure numbers", artifact_materialization: "Saving results",
    },
    errors: {
      input_pdf_invalid: "The PDF could not be read.",
      input_pdf_encrypted: "Password-protected PDFs are unsupported.",
      request_page_out_of_range: "The selected page is outside the PDF.",
      invalid_saved_result: "The saved result could not be verified.",
      local_job_failed: "No result was published. Check the launcher log."
    },
  },
  ja: {
    submitTitle: "PDFに小節番号を付ける", file: "楽譜PDF", pages: "対象ページ（任意）",
    pagesHelp: "ページ番号をカンマで区切ります。空欄の場合は全ページを処理します。",
    start: "番号付けを開始", jobsTitle: "ジョブ一覧", empty: "投入済みのジョブはありません。",
    uploading: "PDFを送信中…", submitted: "ジョブを受け付けました", queued: "処理待ち",
    running: "処理中", succeeded: "番号付きPDFを取得できます · 補正可能",
    review_required: "番号付きPDFを取得できます · 要確認", failed: "失敗",
    interrupted: "中断 · PDFを選び直すと新しいジョブを開始できます",
    open: "番号付きPDFを開く", download: "ダウンロード", review: "補正GUIを開く",
    listError: "ジョブ一覧を取得できません。再接続しています…",
    requestError: "ジョブを送信できませんでした", fileError: "256 MiB以下の空でないPDFを選択してください",
    pagesError: "正のページ番号をカンマで区切って入力してください", busy: "実行中のジョブが終わるまでお待ちください",
    page: "ページ",
    stages: {
      job: "開始処理", input_validation: "入力を検証", pdf_render: "PDFを画像化",
      score_detection: "楽譜を認識", measure_construction: "小節を構成",
      measure_number_recognition: "小節数を読み取り", correction_application: "補正を適用",
      numbering: "小節番号を付与", artifact_materialization: "結果を保存",
    },
    errors: {
      input_pdf_invalid: "PDFを読み込めませんでした。",
      input_pdf_encrypted: "パスワード付きPDFには対応していません。",
      request_page_out_of_range: "指定したページがPDFにありません。",
      invalid_saved_result: "保存済みの結果を検証できませんでした。",
      local_job_failed: "結果を公開できませんでした。起動ログを確認してください。"
    },
  },
};

const byId = id => document.getElementById(id);
let language = localStorage.getItem("pdfscore-job-language") || (navigator.language.startsWith("ja") ? "ja" : "en");
let jobs = [];
let rendered = "";
let submissionStatus = "";
let submissionJobId = "";
let submissionError = "";
const words = () => copy[language] || copy.en;

function render() {
  const text = words();
  document.documentElement.lang = language;
  document.querySelectorAll("[data-copy]").forEach(node => { node.textContent = text[node.dataset.copy]; });
  byId("language").textContent = language === "ja" ? "English" : "日本語";
  byId("submission-status").textContent = submissionJobId
    ? text.submitted + " · " + submissionJobId : text[submissionStatus] || "";
  byId("submission-error").textContent = text[submissionError] || "";
  const snapshot = JSON.stringify([language, jobs]);
  if (snapshot === rendered) return;
  rendered = snapshot;

  const rows = jobs.map(job => {
    const row = document.createElement("li");
    const name = document.createElement("strong");
    name.textContent = job.filename;
    const identity = document.createElement("small");
    identity.textContent = job.id;
    const status = document.createElement("p");
    status.textContent = text[job.status] || job.status;
    if (job.progress) {
      const {stage_id, page_number, completed_units, total_units} = job.progress;
      status.textContent += " · " + (text.stages[stage_id] || stage_id);
      if (page_number) status.textContent += " · " + text.page + " " + page_number;
      if (total_units) status.textContent += " · " + completed_units + " / " + total_units;
    }
    if (job.error) {
      const {code} = job.error;
      status.textContent += " · " + (text.errors[code] || code);
    }
    row.append(name, identity, status);
    if (job.pdf) {
      const open = document.createElement("a");
      open.href = job.pdf;
      open.target = "_blank";
      open.rel = "noopener";
      open.textContent = text.open;
      const download = document.createElement("a");
      download.href = job.pdf;
      download.download = "";
      download.textContent = text.download;
      const review = document.createElement("a");
      review.href = job.review;
      review.textContent = text.review;
      row.append(open, download, review);
    }
    return row;
  });
  byId("jobs").replaceChildren(...rows);
  byId("no-jobs").hidden = jobs.length !== 0;
}

async function poll() {
  try {
    const response = await fetch("/api/jobs");
    if (!response.ok) throw new Error();
    jobs = (await response.json()).jobs;
    byId("list-error").textContent = "";
    render();
  } catch {
    byId("list-error").textContent = words().listError;
  } finally {
    setTimeout(poll, 1000);
  }
}

byId("language").addEventListener("click", () => {
  language = language === "ja" ? "en" : "ja";
  localStorage.setItem("pdfscore-job-language", language);
  render();
});

byId("submit-job").addEventListener("submit", async event => {
  event.preventDefault();
  const file = byId("pdf").files[0];
  const pages = byId("pages").value.trim();
  submissionStatus = "";
  submissionJobId = "";
  submissionError = !file?.size || file.size > 256 * 1024 * 1024 || !/\.pdf$/i.test(file.name) ? "fileError" : "";
  if (pages && !pages.split(",").every(page => /^[1-9][0-9]{0,8}$/.test(page.trim()))) {
    submissionError = "pagesError";
  }
  render();
  if (submissionError) return;
  submissionStatus = "uploading";
  byId("start").disabled = true;
  render();
  try {
    const response = await fetch("/api/jobs", {
      method: "POST", body: file,
      headers: {"Content-Type": "application/pdf", "X-PDF-Name": encodeURIComponent(file.name), "X-PDF-Pages": pages},
    });
    if (!response.ok) {
      submissionStatus = "";
      submissionError = ({400: "pagesError", 409: "busy", 413: "fileError"})[response.status] || "requestError";
    } else {
      const {id} = await response.json();
      if (!/^job-[0-9a-f]{12,32}$/.test(id)) throw new Error("Unexpected job ID");
      submissionJobId = id;
      submissionStatus = "submitted";
      event.target.reset();
    }
  } catch {
    submissionStatus = "";
    submissionError = "requestError";
  } finally {
    byId("start").disabled = false;
    render();
  }
});

render();
poll();
