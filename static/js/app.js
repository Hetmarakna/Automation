/**
 * SmartApply - Frontend Controller & Workflow Engine
 */

// Toast notification helper
function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const bgClass = type === "success" ? "bg-success text-white" :
                    type === "error" ? "bg-danger text-white" :
                    type === "warning" ? "bg-warning text-dark" : "bg-dark text-white";

    const toastEl = document.createElement("div");
    toastEl.className = `toast align-items-center ${bgClass} border-0 shadow-lg`;
    toastEl.setAttribute("role", "alert");
    toastEl.setAttribute("aria-live", "assertive");
    toastEl.setAttribute("aria-atomic", "true");
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body d-flex align-items-center gap-2">
                <span>${message}</span>
            </div>
            <button type="button" class="btn-close ${type === "warning" ? "" : "btn-close-white"} me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    container.appendChild(toastEl);
    const bsToast = new bootstrap.Toast(toastEl, { delay: 4000 });
    bsToast.show();
    toastEl.addEventListener("hidden.bs.toast", () => toastEl.remove());
}

// Global active polling interval for sending campaign
let sendPollInterval = null;

// ==========================================
// 1. IMPORT JOB DETAILS PDF PAGE
// ==========================================
let extractedRecipients = [];

function initImportPage() {
    const dropzone = document.getElementById("pdfDropzone");
    const fileInput = document.getElementById("pdfFileInput");
    const progressContainer = document.getElementById("extractionProgress");
    const resultsContainer = document.getElementById("resultsContainer");

    if (!dropzone || !fileInput) return;

    // Load any existing saved recipients from sessionStorage
    const saved = sessionStorage.getItem("smartapply_recipients");
    if (saved) {
        try {
            extractedRecipients = JSON.parse(saved);
            if (extractedRecipients.length > 0) {
                renderRecipientsTable();
                if (resultsContainer) resultsContainer.classList.remove("d-none");
            }
        } catch (e) {
            console.error(e);
        }
    }

    // Drag-and-drop events
    ["dragenter", "dragover"].forEach(event => {
        dropzone.addEventListener(event, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add("dragover");
        });
    });

    ["dragleave", "drop"].forEach(event => {
        dropzone.addEventListener(event, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove("dragover");
        });
    });

    dropzone.addEventListener("drop", (e) => {
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handlePdfUpload(e.dataTransfer.files[0]);
        }
    });

    dropzone.addEventListener("click", () => fileInput.click());

    fileInput.addEventListener("change", () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handlePdfUpload(fileInput.files[0]);
        }
    });

    // Add Recipient Modal Form
    const addRecipientForm = document.getElementById("addRecipientForm");
    if (addRecipientForm) {
        addRecipientForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const emailInput = document.getElementById("newRecipientEmail");
            const companyInput = document.getElementById("newRecipientCompany");
            const titleInput = document.getElementById("newRecipientTitle");

            const email = (emailInput.value || "").trim().toLowerCase();
            const company = (companyInput.value || "").trim();
            const jobTitle = (titleInput.value || "").trim();

            if (!email) {
                showToast("Please provide a valid email address.", "warning");
                return;
            }

            extractedRecipients.push({
                id: Date.now(),
                email: email,
                company: company,
                job_title: jobTitle,
                source_page: "Manual",
                selected: true
            });

            saveRecipientsToStorage();
            renderRecipientsTable();
            showToast(`Added ${email} to recipients.`, "success");

            // Close modal
            const modalEl = document.getElementById("addRecipientModal");
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            addRecipientForm.reset();
        });
    }

    // Select All / Deselect All
    const selectAllCheckbox = document.getElementById("selectAllCheckbox");
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener("change", () => {
            const isChecked = selectAllCheckbox.checked;
            extractedRecipients.forEach(r => r.selected = isChecked);
            saveRecipientsToStorage();
            renderRecipientsTable();
        });
    }

    // Proceed to Composer button
    const btnProceed = document.getElementById("btnProceedComposer");
    if (btnProceed) {
        btnProceed.addEventListener("click", () => {
            const selectedCount = extractedRecipients.filter(r => r.selected).length;
            if (selectedCount === 0) {
                showToast("Please select at least one recipient before proceeding.", "warning");
                return;
            }
            saveRecipientsToStorage();
            window.location.href = "/composer";
        });
    }
}

function handlePdfUpload(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showToast("Only PDF documents (.pdf) are supported.", "error");
        return;
    }

    const progressContainer = document.getElementById("extractionProgress");
    const resultsContainer = document.getElementById("resultsContainer");
    const scannedAlert = document.getElementById("scannedPdfAlert");

    if (progressContainer) progressContainer.classList.remove("d-none");
    if (scannedAlert) scannedAlert.classList.add("d-none");

    const formData = new FormData();
    formData.append("file", file);

    fetch("/api/upload-pdf", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (progressContainer) progressContainer.classList.add("d-none");

        if (!data.success) {
            showToast(data.error || "Failed to process PDF.", "error");
            return;
        }

        if (data.is_scanned) {
            if (scannedAlert) {
                scannedAlert.classList.remove("d-none");
                const scannedText = document.getElementById("scannedAlertText");
                if (scannedText) scannedText.innerText = data.notice;
            }
        }

        // Merge or replace recipients
        extractedRecipients = data.recipients || [];
        saveRecipientsToStorage();
        renderRecipientsTable();

        if (resultsContainer) resultsContainer.classList.remove("d-none");

        const filenameSpan = document.getElementById("sourceFilename");
        if (filenameSpan) filenameSpan.innerText = data.filename;

        const noticeSpan = document.getElementById("extractionNotice");
        if (noticeSpan) noticeSpan.innerText = data.notice;

        showToast(`Extracted ${extractedRecipients.length} recipients.`, "success");
    })
    .catch(err => {
        if (progressContainer) progressContainer.classList.add("d-none");
        showToast("Error uploading PDF: " + err.message, "error");
    });
}

function saveRecipientsToStorage() {
    sessionStorage.setItem("smartapply_recipients", JSON.stringify(extractedRecipients));
    updateRecipientCounterBadge();
}

function updateRecipientCounterBadge() {
    const totalCount = extractedRecipients.length;
    const selectedCount = extractedRecipients.filter(r => r.selected).length;

    const countEls = document.querySelectorAll(".recipient-selected-count");
    countEls.forEach(el => el.innerText = selectedCount);

    const totalEls = document.querySelectorAll(".recipient-total-count");
    totalEls.forEach(el => el.innerText = totalCount);
}

function renderRecipientsTable() {
    const tbody = document.getElementById("recipientsTableBody");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (extractedRecipients.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center py-4 text-muted">
                    No recipients extracted yet. Upload a PDF or add recipients manually.
                </td>
            </tr>
        `;
        updateRecipientCounterBadge();
        return;
    }

    extractedRecipients.forEach((rec, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td style="width: 40px;" class="text-center">
                <input type="checkbox" class="form-check-input recipient-checkbox" data-idx="${idx}" ${rec.selected ? "checked" : ""}>
            </td>
            <td>
                <span class="fw-semibold text-dark">${escapeHtml(rec.email)}</span>
                <span class="badge badge-sa-neutral ms-1">${escapeHtml(String(rec.source_page || "PDF"))}</span>
            </td>
            <td>
                <input type="text" class="form-control form-control-sm editable-company" data-idx="${idx}" value="${escapeHtml(rec.company || "")}" placeholder="Company name">
            </td>
            <td>
                <input type="text" class="form-control form-control-sm editable-job" data-idx="${idx}" value="${escapeHtml(rec.job_title || "")}" placeholder="Job title">
            </td>
            <td class="text-end" style="width: 80px;">
                <button type="button" class="btn btn-sm btn-outline-danger btn-remove-recipient" data-idx="${idx}" title="Remove">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });

    // Wire up events
    tbody.querySelectorAll(".recipient-checkbox").forEach(chk => {
        chk.addEventListener("change", (e) => {
            const idx = parseInt(e.target.getAttribute("data-idx"));
            extractedRecipients[idx].selected = e.target.checked;
            saveRecipientsToStorage();
        });
    });

    tbody.querySelectorAll(".editable-company").forEach(input => {
        input.addEventListener("input", (e) => {
            const idx = parseInt(e.target.getAttribute("data-idx"));
            extractedRecipients[idx].company = e.target.value;
            saveRecipientsToStorage();
        });
    });

    tbody.querySelectorAll(".editable-job").forEach(input => {
        input.addEventListener("input", (e) => {
            const idx = parseInt(e.target.getAttribute("data-idx"));
            extractedRecipients[idx].job_title = e.target.value;
            saveRecipientsToStorage();
        });
    });

    tbody.querySelectorAll(".btn-remove-recipient").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const idx = parseInt(btn.getAttribute("data-idx"));
            extractedRecipients.splice(idx, 1);
            saveRecipientsToStorage();
            renderRecipientsTable();
        });
    });

    updateRecipientCounterBadge();
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// ==========================================
// 2. EMAIL COMPOSER PAGE
// ==========================================
function initComposerPage() {
    const subjectInput = document.getElementById("emailSubject");
    const bodyTextarea = document.getElementById("emailBody");
    const nameInput = document.getElementById("candidateName");
    const contactInput = document.getElementById("candidateContact");
    const delayInput = document.getElementById("delaySeconds");
    const batchLimitInput = document.getElementById("batchLimit");
    const recipientSelect = document.getElementById("previewRecipientSelect");

    // Load recipients from storage
    const savedRecipients = sessionStorage.getItem("smartapply_recipients");
    if (savedRecipients) {
        try {
            extractedRecipients = JSON.parse(savedRecipients);
        } catch (e) {
            extractedRecipients = [];
        }
    }

    // Populate preview recipient selector
    if (recipientSelect) {
        recipientSelect.innerHTML = "";
        const activeList = extractedRecipients.filter(r => r.selected);
        if (activeList.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.innerText = "Sample Recipient (careers@acme.com)";
            recipientSelect.appendChild(opt);
        } else {
            activeList.forEach((r, idx) => {
                const opt = document.createElement("option");
                opt.value = idx;
                opt.innerText = `${r.email} (${r.company || "No Company"} — ${r.job_title || "No Title"})`;
                recipientSelect.appendChild(opt);
            });
        }
        recipientSelect.addEventListener("change", updateLivePreview);
    }

    // Tag pills click to insert placeholder at cursor
    document.querySelectorAll(".tag-pill").forEach(pill => {
        pill.addEventListener("click", () => {
            const tag = pill.getAttribute("data-tag");
            const targetId = pill.getAttribute("data-target") || "emailBody";
            const targetEl = document.getElementById(targetId);
            if (targetEl) {
                insertAtCursor(targetEl, tag);
                updateLivePreview();
            }
        });
    });

    // Live preview update triggers
    if (subjectInput) subjectInput.addEventListener("input", updateLivePreview);
    if (bodyTextarea) bodyTextarea.addEventListener("input", updateLivePreview);
    if (nameInput) nameInput.addEventListener("input", updateLivePreview);
    if (contactInput) contactInput.addEventListener("input", updateLivePreview);

    // Initial preview render
    updateLivePreview();
    updateRecipientCounterBadge();

    // Reset Template Button
    const btnReset = document.getElementById("btnResetTemplate");
    if (btnReset) {
        btnReset.addEventListener("click", () => {
            if (confirm("Reset subject and body back to default professional template?")) {
                if (subjectInput) subjectInput.value = "Application for {job_title} — {your_name}";
                if (bodyTextarea) bodyTextarea.value = `Dear Hiring Team,\n\nI hope you are doing well.\n\nI am writing to express my interest in the {job_title} position at {company}. Please find my resume attached for your consideration.\n\nI would welcome the opportunity to discuss how my skills and experience align with your requirements.\n\nThank you for your time and consideration.\n\nBest regards,\n{your_name}\n{your_contact}`;
                updateLivePreview();
                showToast("Template reset to default.", "info");
            }
        });
    }

    // Save Template Settings Button
    const btnSaveTemplate = document.getElementById("btnSaveTemplate");
    if (btnSaveTemplate) {
        btnSaveTemplate.addEventListener("click", () => {
            const payload = {
                subject: subjectInput.value,
                body: bodyTextarea.value,
                candidate_name: nameInput.value,
                candidate_contact: contactInput.value,
                delay_seconds: parseFloat(delayInput.value) || 2.0,
                batch_limit: parseInt(batchLimitInput.value) || 5
            };

            fetch("/api/template", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    showToast("Template settings saved successfully.", "success");
                } else {
                    showToast(data.message || "Failed to save template.", "error");
                }
            })
            .catch(err => showToast(err.message, "error"));
        });
    }

    // Resume Upload in Composer
    initResumeUploader();

    // Send Test Email Button & Modal
    const btnOpenTestModal = document.getElementById("btnOpenTestEmailModal");
    const testModalEl = document.getElementById("testEmailModal");
    const sendTestForm = document.getElementById("sendTestForm");

    if (btnOpenTestModal && testModalEl) {
        btnOpenTestModal.addEventListener("click", () => {
            const modal = new bootstrap.Modal(testModalEl);
            modal.show();
        });
    }

    if (sendTestForm) {
        sendTestForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const recipient = document.getElementById("testRecipientEmail").value.trim();
            const btnSubmit = document.getElementById("btnSendTestSubmit");
            const spinner = document.getElementById("testEmailSpinner");

            if (!recipient) {
                showToast("Please enter a test recipient email.", "warning");
                return;
            }

            if (btnSubmit) btnSubmit.disabled = true;
            if (spinner) spinner.classList.remove("d-none");

            const payload = {
                test_recipient: recipient,
                subject: subjectInput.value,
                body: bodyTextarea.value,
                candidate_name: nameInput.value,
                candidate_contact: contactInput.value
            };

            fetch("/api/send/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (btnSubmit) btnSubmit.disabled = false;
                if (spinner) spinner.classList.add("d-none");

                if (data.success) {
                    showToast(data.message, "success");
                    const modal = bootstrap.Modal.getInstance(testModalEl);
                    if (modal) modal.hide();
                } else {
                    showToast(data.message || "Test email failed.", "error");
                }
            })
            .catch(err => {
                if (btnSubmit) btnSubmit.disabled = false;
                if (spinner) spinner.classList.add("d-none");
                showToast("Error sending test email: " + err.message, "error");
            });
        });
    }

    // Review & Send Campaign Button
    const btnReviewCampaign = document.getElementById("btnReviewCampaign");
    const reviewModalEl = document.getElementById("reviewCampaignModal");
    if (btnReviewCampaign && reviewModalEl) {
        btnReviewCampaign.addEventListener("click", () => {
            const selectedList = extractedRecipients.filter(r => r.selected);
            if (selectedList.length === 0) {
                showToast("No recipients selected! Please import a PDF or add recipients first.", "warning");
                return;
            }

            const limitVal = parseInt(batchLimitInput ? batchLimitInput.value : 5) || 5;
            const willSendCount = Math.min(selectedList.length, limitVal);

            const countEl = document.getElementById("reviewSelectedCount");
            const batchEl = document.getElementById("reviewBatchLimit");
            const delayEl = document.getElementById("reviewDelay");
            const willSendEl = document.getElementById("reviewWillSendCount");

            if (countEl) countEl.innerText = selectedList.length;
            if (batchEl) batchEl.innerText = limitVal;
            if (delayEl) delayEl.innerText = (delayInput ? delayInput.value : "2.0") + "s";
            if (willSendEl) willSendEl.innerText = willSendCount;

            const modal = new bootstrap.Modal(reviewModalEl);
            modal.show();
        });
    }

    // Explicit Confirm & Launch Send Button
    const btnConfirmSend = document.getElementById("btnConfirmSend");
    if (btnConfirmSend) {
        btnConfirmSend.addEventListener("click", () => {
            // Close review modal
            const reviewModal = bootstrap.Modal.getInstance(reviewModalEl);
            if (reviewModal) reviewModal.hide();

            // Start bulk send campaign
            startBulkSendCampaign();
        });
    }
}

function updateLivePreview() {
    const subjectInput = document.getElementById("emailSubject");
    const bodyTextarea = document.getElementById("emailBody");
    const nameInput = document.getElementById("candidateName");
    const contactInput = document.getElementById("candidateContact");
    const recipientSelect = document.getElementById("previewRecipientSelect");

    const previewSubject = document.getElementById("previewSubjectText");
    const previewTo = document.getElementById("previewToText");
    const previewBody = document.getElementById("previewBodyText");

    if (!previewSubject || !previewBody) return;

    // Determine current recipient data
    let sampleRecipient = {
        email: "recruiter@innovations.com",
        company: "Innovations Inc.",
        job_title: "Senior Python Developer"
    };

    const activeList = extractedRecipients.filter(r => r.selected);
    if (recipientSelect && recipientSelect.value !== "" && activeList[recipientSelect.value]) {
        const selected = activeList[recipientSelect.value];
        sampleRecipient = {
            email: selected.email,
            company: selected.company || "the hiring team",
            job_title: selected.job_title || "the open position"
        };
    }

    const yourName = (nameInput ? nameInput.value : "") || "Applicant";
    const yourContact = (contactInput ? contactInput.value : "") || "";

    const rawSubject = (subjectInput ? subjectInput.value : "") || "Application for {job_title} — {your_name}";
    const rawBody = (bodyTextarea ? bodyTextarea.value : "") || "";

    // Replace placeholders
    const replaceVars = (str) => {
        return str
            .replace(/{company}/g, sampleRecipient.company)
            .replace(/{job_title}/g, sampleRecipient.job_title)
            .replace(/{your_name}/g, yourName)
            .replace(/{your_contact}/g, yourContact)
            .replace(/{recipient_email}/g, sampleRecipient.email);
    };

    previewSubject.innerText = replaceVars(rawSubject);
    previewBody.innerText = replaceVars(rawBody);
    if (previewTo) previewTo.innerText = sampleRecipient.email;
}

function insertAtCursor(input, textToInsert) {
    const start = input.selectionStart || 0;
    const end = input.selectionEnd || 0;
    const val = input.value;
    input.value = val.substring(0, start) + textToInsert + val.substring(end);
    input.selectionStart = input.selectionEnd = start + textToInsert.length;
    input.focus();
}

function initResumeUploader() {
    const resumeDropzone = document.getElementById("resumeDropzone");
    const resumeFileInput = document.getElementById("resumeFileInput");
    const resumeInfoCard = document.getElementById("resumeInfoCard");
    const btnRemoveResume = document.getElementById("btnRemoveResume");

    if (resumeDropzone && resumeFileInput) {
        resumeDropzone.addEventListener("click", () => resumeFileInput.click());

        resumeFileInput.addEventListener("change", () => {
            if (resumeFileInput.files && resumeFileInput.files.length > 0) {
                uploadResumeFile(resumeFileInput.files[0]);
            }
        });

        ["dragenter", "dragover"].forEach(event => {
            resumeDropzone.addEventListener(event, (e) => {
                e.preventDefault();
                resumeDropzone.classList.add("dragover");
            });
        });

        ["dragleave", "drop"].forEach(event => {
            resumeDropzone.addEventListener(event, (e) => {
                e.preventDefault();
                resumeDropzone.classList.remove("dragover");
            });
        });

        resumeDropzone.addEventListener("drop", (e) => {
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                uploadResumeFile(e.dataTransfer.files[0]);
            }
        });
    }

    if (btnRemoveResume) {
        btnRemoveResume.addEventListener("click", () => {
            if (confirm("Remove attached resume?")) {
                fetch("/api/remove-resume", { method: "POST" })
                .then(res => res.json())
                .then(() => {
                    if (resumeInfoCard) resumeInfoCard.classList.add("d-none");
                    if (resumeDropzone) resumeDropzone.classList.remove("d-none");
                    showToast("Resume removed.", "info");
                });
            }
        });
    }
}

function uploadResumeFile(file) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
        showToast("Resume must be a PDF document (.pdf).", "error");
        return;
    }

    const formData = new FormData();
    formData.append("resume", file);

    fetch("/api/upload-resume", {
        method: "POST",
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, "success");
            const resumeInfoCard = document.getElementById("resumeInfoCard");
            const resumeDropzone = document.getElementById("resumeDropzone");
            const resumeNameSpan = document.getElementById("resumeFilenameDisplay");
            const resumeSizeSpan = document.getElementById("resumeFilesizeDisplay");

            if (resumeNameSpan) resumeNameSpan.innerText = data.filename;
            if (resumeSizeSpan) resumeSizeSpan.innerText = `(${data.size_kb} KB)`;
            if (resumeDropzone) resumeDropzone.classList.add("d-none");
            if (resumeInfoCard) resumeInfoCard.classList.remove("d-none");
        } else {
            showToast(data.error || "Failed to upload resume.", "error");
        }
    })
    .catch(err => showToast("Error uploading resume: " + err.message, "error"));
}

// ==========================================
// 3. CONTROLLED BULK SENDING MODAL & ENGINE
// ==========================================
function startBulkSendCampaign() {
    const subjectInput = document.getElementById("emailSubject");
    const bodyTextarea = document.getElementById("emailBody");
    const nameInput = document.getElementById("candidateName");
    const contactInput = document.getElementById("candidateContact");
    const delayInput = document.getElementById("delaySeconds");
    const batchLimitInput = document.getElementById("batchLimit");

    const payload = {
        recipients: extractedRecipients,
        subject: subjectInput.value,
        body: bodyTextarea.value,
        candidate_name: nameInput.value,
        candidate_contact: contactInput.value,
        delay_seconds: parseFloat(delayInput ? delayInput.value : 2.0) || 2.0,
        batch_limit: parseInt(batchLimitInput ? batchLimitInput.value : 5) || 5
    };

    fetch("/api/send/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (!data.success) {
            showToast(data.message || "Failed to start campaign.", "error");
            return;
        }

        // Open Sending Modal
        openSendingModal();
    })
    .catch(err => showToast("Error starting send campaign: " + err.message, "error"));
}

function openSendingModal() {
    const modalEl = document.getElementById("sendingModal");
    if (!modalEl) return;

    const modal = new bootstrap.Modal(modalEl, { backdrop: "static", keyboard: false });
    modal.show();

    // Start polling campaign progress
    if (sendPollInterval) clearInterval(sendPollInterval);
    sendPollInterval = setInterval(pollCampaignStatus, 800);
}

function pollCampaignStatus() {
    fetch("/api/send/status")
    .then(res => res.json())
    .then(state => {
        const progressBar = document.getElementById("campaignProgressBar");
        const statusBadge = document.getElementById("campaignStatusBadge");
        const currentRecipient = document.getElementById("campaignCurrentRecipient");
        const sentCount = document.getElementById("campaignSentCount");
        const failedCount = document.getElementById("campaignFailedCount");
        const skippedCount = document.getElementById("campaignSkippedCount");
        const totalCount = document.getElementById("campaignTotalCount");
        const consoleBox = document.getElementById("campaignConsoleLogs");

        const btnPause = document.getElementById("btnPauseCampaign");
        const btnResume = document.getElementById("btnResumeCampaign");
        const btnCancel = document.getElementById("btnCancelCampaign");
        const btnDone = document.getElementById("btnDoneCampaign");

        if (progressBar) {
            progressBar.style.width = `${state.percent}%`;
            progressBar.innerText = `${state.percent}%`;
        }

        if (sentCount) sentCount.innerText = state.sent;
        if (failedCount) failedCount.innerText = state.failed;
        if (skippedCount) skippedCount.innerText = state.skipped;
        if (totalCount) totalCount.innerText = state.total;

        if (currentRecipient) {
            currentRecipient.innerText = state.current_recipient ? `Processing: ${state.current_recipient}` : `Status: ${state.status}`;
        }

        if (statusBadge) {
            statusBadge.innerText = state.status.toUpperCase();
            if (state.status === "running") {
                statusBadge.className = "badge bg-primary";
                if (btnPause) btnPause.classList.remove("d-none");
                if (btnResume) btnResume.classList.add("d-none");
                if (btnCancel) btnCancel.classList.remove("d-none");
                if (btnDone) btnDone.classList.add("d-none");
            } else if (state.status === "paused") {
                statusBadge.className = "badge bg-warning text-dark";
                if (btnPause) btnPause.classList.add("d-none");
                if (btnResume) btnResume.classList.remove("d-none");
            } else if (state.status === "completed") {
                statusBadge.className = "badge bg-success";
                if (btnPause) btnPause.classList.add("d-none");
                if (btnResume) btnResume.classList.add("d-none");
                if (btnCancel) btnCancel.classList.add("d-none");
                if (btnDone) btnDone.classList.remove("d-none");
                clearInterval(sendPollInterval);
            } else if (state.status === "cancelled") {
                statusBadge.className = "badge bg-danger";
                if (btnPause) btnPause.classList.add("d-none");
                if (btnResume) btnResume.classList.add("d-none");
                if (btnCancel) btnCancel.classList.add("d-none");
                if (btnDone) btnDone.classList.remove("d-none");
                clearInterval(sendPollInterval);
            }
        }

        // Render console logs
        if (consoleBox && state.logs) {
            consoleBox.innerHTML = "";
            state.logs.forEach(log => {
                const line = document.createElement("div");
                line.className = `console-line ${log.type}`;
                line.innerText = `[${log.timestamp}] ${log.message}`;
                consoleBox.appendChild(line);
            });
            consoleBox.scrollTop = consoleBox.scrollHeight;
        }
    })
    .catch(err => console.error("Poll status error:", err));
}

function initCampaignControls() {
    const btnPause = document.getElementById("btnPauseCampaign");
    const btnResume = document.getElementById("btnResumeCampaign");
    const btnCancel = document.getElementById("btnCancelCampaign");

    if (btnPause) {
        btnPause.addEventListener("click", () => {
            fetch("/api/send/pause", { method: "POST" })
            .then(res => res.json())
            .then(data => showToast(data.message, data.success ? "info" : "error"));
        });
    }

    if (btnResume) {
        btnResume.addEventListener("click", () => {
            fetch("/api/send/resume", { method: "POST" })
            .then(res => res.json())
            .then(data => showToast(data.message, data.success ? "info" : "error"));
        });
    }

    if (btnCancel) {
        btnCancel.addEventListener("click", () => {
            if (confirm("Are you sure you want to cancel the rest of the campaign? Currently processing emails will complete.")) {
                fetch("/api/send/cancel", { method: "POST" })
                .then(res => res.json())
                .then(data => showToast(data.message, "warning"));
            }
        });
    }
}

// ==========================================
// 4. SMTP SETTINGS PAGE
// ==========================================
function initSmtpPage() {
    const providerSelect = document.getElementById("smtpPreset");
    const hostInput = document.getElementById("smtpHost");
    const portInput = document.getElementById("smtpPort");
    const securitySelect = document.getElementById("smtpSecurity");
    const senderEmailInput = document.getElementById("smtpSenderEmail");
    const senderNameInput = document.getElementById("smtpSenderName");
    const passwordInput = document.getElementById("smtpPassword");
    const togglePasswordBtn = document.getElementById("btnTogglePassword");
    const btnTestConnection = document.getElementById("btnTestSmtp");
    const formSaveSmtp = document.getElementById("smtpConfigForm");

    // Provider preset shortcuts
    if (providerSelect) {
        providerSelect.addEventListener("change", () => {
            const val = providerSelect.value;
            if (val === "gmail") {
                hostInput.value = "smtp.gmail.com";
                portInput.value = "587";
                securitySelect.value = "STARTTLS";
            } else if (val === "outlook") {
                hostInput.value = "smtp.office365.com";
                portInput.value = "587";
                securitySelect.value = "STARTTLS";
            } else if (val === "yahoo") {
                hostInput.value = "smtp.mail.yahoo.com";
                portInput.value = "465";
                securitySelect.value = "SSL/TLS";
            }
        });
    }

    // Toggle password visibility
    if (togglePasswordBtn && passwordInput) {
        togglePasswordBtn.addEventListener("click", () => {
            const isPassword = passwordInput.getAttribute("type") === "password";
            passwordInput.setAttribute("type", isPassword ? "text" : "password");
            togglePasswordBtn.innerText = isPassword ? "Hide" : "Show";
        });
    }

    // Test Connection Button
    if (btnTestConnection) {
        btnTestConnection.addEventListener("click", () => {
            const alertBox = document.getElementById("smtpTestAlert");
            const spinner = document.getElementById("testSmtpSpinner");

            if (alertBox) alertBox.classList.add("d-none");
            if (spinner) spinner.classList.remove("d-none");
            btnTestConnection.disabled = true;

            const payload = {
                host: hostInput.value.trim(),
                port: portInput.value.trim(),
                security: securitySelect.value,
                sender_email: senderEmailInput.value.trim(),
                password: passwordInput.value.trim()
            };

            fetch("/api/test-smtp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                btnTestConnection.disabled = false;
                if (spinner) spinner.classList.add("d-none");

                if (alertBox) {
                    alertBox.classList.remove("d-none", "alert-success", "alert-danger");
                    alertBox.classList.add(data.success ? "alert-success" : "alert-danger");
                    alertBox.innerHTML = `<strong>${data.success ? "Success!" : "Connection Failed:"}</strong> ${escapeHtml(data.message)}`;
                }
            })
            .catch(err => {
                btnTestConnection.disabled = false;
                if (spinner) spinner.classList.add("d-none");
                if (alertBox) {
                    alertBox.classList.remove("d-none", "alert-success");
                    alertBox.classList.add("alert-danger");
                    alertBox.innerText = "Error: " + err.message;
                }
            });
        });
    }

    // Save SMTP Settings Form
    if (formSaveSmtp) {
        formSaveSmtp.addEventListener("submit", (e) => {
            e.preventDefault();
            const btnSave = document.getElementById("btnSaveSmtp");
            if (btnSave) btnSave.disabled = true;

            const payload = {
                host: hostInput.value.trim(),
                port: parseInt(portInput.value.trim()) || 587,
                security: securitySelect.value,
                sender_email: senderEmailInput.value.trim(),
                sender_name: senderNameInput.value.trim(),
                password: passwordInput.value.trim()
            };

            fetch("/api/save-smtp", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if (btnSave) btnSave.disabled = false;
                if (data.success) {
                    showToast(data.message, "success");
                    // Clear password field to avoid keeping it in DOM
                    if (passwordInput && passwordInput.value) {
                        passwordInput.value = "";
                        passwordInput.placeholder = "•••••••••••••••• (Password Saved)";
                    }
                } else {
                    showToast(data.message || "Failed to save SMTP settings.", "error");
                }
            })
            .catch(err => {
                if (btnSave) btnSave.disabled = false;
                showToast("Error saving SMTP: " + err.message, "error");
            });
        });
    }
}

// ==========================================
// 5. APPLICATION HISTORY PAGE
// ==========================================
function initHistoryPage() {
    const searchInput = document.getElementById("historySearch");
    const statusFilter = document.getElementById("historyStatusFilter");
    const btnClearHistory = document.getElementById("btnClearHistory");

    function fetchHistory() {
        const q = searchInput ? searchInput.value.trim() : "";
        const s = statusFilter ? statusFilter.value : "";
        const url = `/api/history?search=${encodeURIComponent(q)}&status=${encodeURIComponent(s)}`;

        fetch(url)
        .then(res => res.json())
        .then(data => {
            renderHistoryRows(data.records);
        });
    }

    if (searchInput) searchInput.addEventListener("input", debounce(fetchHistory, 300));
    if (statusFilter) statusFilter.addEventListener("change", fetchHistory);

    if (btnClearHistory) {
        btnClearHistory.addEventListener("click", () => {
            if (confirm("Are you sure you want to permanently clear all application history records?")) {
                fetch("/api/history/clear", { method: "POST" })
                .then(res => res.json())
                .then(data => {
                    showToast("History cleared.", "info");
                    fetchHistory();
                });
            }
        });
    }

    // Details Modal Trigger
    const historyTableBody = document.getElementById("historyTableBody");
    if (historyTableBody) {
        historyTableBody.addEventListener("click", (e) => {
            const btn = e.target.closest(".btn-history-details");
            if (btn) {
                const subject = btn.getAttribute("data-subject");
                const snippet = btn.getAttribute("data-snippet");
                const error = btn.getAttribute("data-error");
                const resume = btn.getAttribute("data-resume");

                const modalSub = document.getElementById("modalDetailSubject");
                const modalSnip = document.getElementById("modalDetailSnippet");
                const modalErr = document.getElementById("modalDetailError");
                const modalRes = document.getElementById("modalDetailResume");

                if (modalSub) modalSub.innerText = subject;
                if (modalSnip) modalSnip.innerText = snippet || "No body content stored.";
                if (modalRes) modalRes.innerText = resume || "None";

                if (modalErr) {
                    if (error) {
                        modalErr.innerText = error;
                        modalErr.parentElement.classList.remove("d-none");
                    } else {
                        modalErr.parentElement.classList.add("d-none");
                    }
                }

                const modal = new bootstrap.Modal(document.getElementById("historyDetailsModal"));
                modal.show();
            }
        });
    }
}

function renderHistoryRows(records) {
    const tbody = document.getElementById("historyTableBody");
    if (!tbody) return;

    tbody.innerHTML = "";
    if (!records || records.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4 text-muted">
                    No application history records found.
                </td>
            </tr>
        `;
        return;
    }

    records.forEach(r => {
        let statusBadge = `<span class="badge badge-sa-neutral">${escapeHtml(r.status)}</span>`;
        if (r.status === "Sent to SMTP server") {
            statusBadge = `<span class="badge badge-sa-success">✓ Sent to SMTP server</span>`;
        } else if (r.status === "Failed") {
            statusBadge = `<span class="badge badge-sa-danger">✗ Failed</span>`;
        } else if (r.status.startsWith("Skipped")) {
            statusBadge = `<span class="badge badge-sa-warning">⊘ ${escapeHtml(r.status)}</span>`;
        }

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="fw-semibold text-dark">${escapeHtml(r.recipient_email)}</td>
            <td>${escapeHtml(r.company_name || "—")}</td>
            <td>${escapeHtml(r.job_title || "—")}</td>
            <td>${statusBadge}</td>
            <td class="text-muted small">${escapeHtml(r.created_at)}</td>
            <td class="text-end">
                <button type="button" class="btn btn-sm btn-outline-secondary btn-history-details"
                    data-subject="${escapeHtml(r.subject)}"
                    data-snippet="${escapeHtml(r.body_snippet)}"
                    data-error="${escapeHtml(r.error_message || "")}"
                    data-resume="${escapeHtml(r.resume_name || "")}">
                    Details
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Document Ready Initialization
document.addEventListener("DOMContentLoaded", () => {
    initImportPage();
    initComposerPage();
    initCampaignControls();
    initSmtpPage();
    initHistoryPage();
});
