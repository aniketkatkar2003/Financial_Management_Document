const API_BASE_URL = 'http://127.0.0.1:8000'; 

let token = localStorage.getItem("token") || null;
let currentUser = null;
let userRoles = [];
let userPermissions = [];

// DOM Elements.
const authContainer = document.getElementById("auth-container");
const dashboardContainer = document.getElementById("dashboard-container");
const authTabs = document.querySelectorAll(".auth-tab");
const loginForm = document.getElementById("login-form");
const registerForm = document.getElementById("register-form");
const authSwitchText = document.getElementById("auth-switch-text");

const navLinks = document.querySelectorAll(".nav-link");
const contentPanels = document.querySelectorAll(".content-panel");
const panelTitle = document.getElementById("panel-title");
const panelSubtitle = document.getElementById("panel-subtitle");

// Profile & Widget elements
const userDisplayName = document.getElementById("user-display-name");
const userDisplayRole = document.getElementById("user-display-role");
const userDisplayCompany = document.getElementById("user-display-company");
const profEmail = document.getElementById("prof-email");
const profCompany = document.getElementById("prof-company");
const profRoles = document.getElementById("prof-roles");
const btnLogout = document.getElementById("btn-logout");

const statDocCount = document.getElementById("stat-doc-count");
const statChunkCount = document.getElementById("stat-chunk-count");
const statUserPermission = document.getElementById("stat-user-permission");

// Document elements
const documentsTableBody = document.getElementById("documents-table-body");
const btnTriggerUploadModal = document.getElementById("btn-trigger-upload-modal");
const uploadModal = document.getElementById("upload-modal");
const btnCloseUploadModal = document.getElementById("btn-close-upload-modal");
const btnCancelUpload = document.getElementById("btn-cancel-upload");
const uploadDocumentForm = document.getElementById("upload-document-form");
const docFilterTitle = document.getElementById("doc-filter-title");
const docFilterCompany = document.getElementById("doc-filter-company");
const docFilterType = document.getElementById("doc-filter-type");
const btnFilterSearch = document.getElementById("btn-filter-search");

// RAG Elements
const chatMessagesLog = document.getElementById("chat-messages-log");
const chatQueryForm = document.getElementById("chat-query-form");
const chatQueryInput = document.getElementById("chat-query-input");
const btnSubmitQuery = document.getElementById("btn-submit-query");
const sampleQueryBtns = document.querySelectorAll(".sample-query-btn");
const sourcesContainer = document.getElementById("sources-container");
const sourceChunksGrid = document.getElementById("source-chunks-grid");

const rbacAssignForm = document.getElementById("rbac-assign-form");
const rbacUserId = document.getElementById("rbac-user-id");
const rbacRoleName = document.getElementById("rbac-role-name");
const navRbacLink = document.getElementById("nav-rbac-link");

// Helper Functions 

function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    
    let icon = "fa-circle-check";
    if (type === "error") icon = "fa-circle-xmark";
    if (type === "info") icon = "fa-circle-info";
    
    toast.innerHTML = `
        <i class="fa-solid ${icon}"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

async function apiRequest(endpoint, method = "GET", body = null, isMultipart = false) {
    const headers = {};
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    if (!isMultipart && method !== "GET") {
        headers["Content-Type"] = "application/json";
    }

    const config = {
        method,
        headers
    };

    if (body) {
        config.body = isMultipart ? body : JSON.stringify(body);
    }

    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
        
        if (response.status === 401) {
            handleLogout();
            showToast("Session expired. Please log in again.", "error");
            throw new Error("Unauthorized");
        }

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "API operation failed");
        }
        return data;
    } catch (error) {
        console.error(`API Error on ${endpoint}:`, error);
        throw error;
    }
}

//Session & Hydration

async function initSession() {
    if (!token) {
        showAuthScreen();
        return;
    }
    
    try {
        const decoded = parseJwt(token);
        if (!decoded || !decoded.user_id) {
            handleLogout();
            return;
        }

        
        const [rolesData, permsData] = await Promise.all([
            apiRequest(`/users/${decoded.user_id}/roles`),
            apiRequest(`/users/${decoded.user_id}/permissions`)
        ]);

        userRoles = rolesData.roles;
        userPermissions = permsData.permissions;
        
        
        currentUser = {
            id: decoded.user_id,
            username: decoded.sub,
            roles: userRoles,
            permissions: userPermissions
        };

        
        userDisplayName.innerText = currentUser.username;
        userDisplayRole.innerText = userRoles.join(", ");
        
        
        showDashboardScreen();
        await loadDashboardOverview();
        
        
        const isAdmin = userRoles.some(r => r.toLowerCase() === "admin");
        if (isAdmin) {
            navRbacLink.parentElement.classList.remove("hidden");
        } else {
            navRbacLink.parentElement.classList.add("hidden");
        }
        
        
        const isClient = userRoles.some(r => r.toLowerCase() === "client");
        if (isClient) {
            btnTriggerUploadModal.classList.add("hidden");
        } else {
            btnTriggerUploadModal.classList.remove("hidden");
        }
        
    } catch (error) {
        handleLogout();
    }
}

function showAuthScreen() {
    authContainer.classList.remove("hidden");
    dashboardContainer.classList.add("hidden");
}

function showDashboardScreen() {
    authContainer.classList.add("hidden");
    dashboardContainer.classList.remove("hidden");
}

function handleLogout() {
    token = null;
    currentUser = null;
    userRoles = [];
    userPermissions = [];
    localStorage.removeItem("token");
    showAuthScreen();
    showToast("Successfully logged out.", "info");
}

//Overview Dashboard
async function loadDashboardOverview() {
    try {
        const docs = await apiRequest("/documents");
        statDocCount.innerText = docs.length;
        
        
        const companyName = docs.length > 0 ? docs[0].company_name : "NMap InfoTech";
        
        userDisplayCompany.innerText = companyName;
        profCompany.innerText = companyName;
        profRoles.innerText = userRoles.join(", ");
        
        
        profEmail.innerText = `${currentUser.username}@nmapinfotech.com`;

        
        let totalChunks = 0;
        if (docs.length > 0) {
            
            try {
                const sampleCtx = await apiRequest(`/rag/context/${docs[0].document_id}`);
                totalChunks = sampleCtx.chunks_count * docs.length; 
            } catch (e) {
                totalChunks = docs.length * 15; 
            }
        }
        statChunkCount.innerText = totalChunks;

        
        statUserPermission.innerText = userPermissions.includes("full_access") ? "Full root Access" : `${userPermissions.length} Active rules`;

    } catch (error) {
        console.error("Overview hydration failed:", error);
    }
}

//Documents View

async function fetchDocuments(title = "", company = "", type = "") {
    try {
        documentsTableBody.innerHTML = `<tr><td colspan="6" class="text-center">Filtering documents...</td></tr>`;
        
        let endpoint = "/documents";
        const params = [];
        if (title) params.push(`title=${encodeURIComponent(title)}`);
        if (company) params.push(`company_name=${encodeURIComponent(company)}`);
        if (type) params.push(`document_type=${encodeURIComponent(type)}`);
        
        if (params.length > 0) {
            endpoint = `/documents/search?${params.join("&")}`;
        }
        
        const docs = await apiRequest(endpoint);
        renderDocumentsTable(docs);
    } catch (error) {
        showToast("Failed to fetch documents.", "error");
    }
}

function renderDocumentsTable(documents) {
    if (documents.length === 0) {
        documentsTableBody.innerHTML = `<tr><td colspan="6" class="text-center">No documents indexed in your company scope.</td></tr>`;
        return;
    }

    const isAdmin = userRoles.some(r => r.toLowerCase() === "admin");
    const isClient = userRoles.some(r => r.toLowerCase() === "client");

    documentsTableBody.innerHTML = documents.map(doc => {
        const createdDate = new Date(doc.created_at).toLocaleDateString("en-US", {
            year: "numeric", month: "short", day: "numeric"
        });

        const editButton = isAdmin 
            ? `<button class="btn-action btn-edit" onclick="handleEditDocument('${doc.document_id}')" title="Edit Document"><i class="fa-solid fa-pencil"></i></button>`
            : "";

        const deleteButton = isAdmin 
            ? `<button class="btn-action btn-delete" onclick="handleDeleteDocument('${doc.document_id}')" title="Delete Document"><i class="fa-solid fa-trash"></i></button>`
            : "";
            
        return `
            <tr>
                <td><strong>${doc.title}</strong></td>
                <td>${doc.company_name}</td>
                <td><span class="badge-type ${doc.document_type}">${doc.document_type}</span></td>
                <td>${createdDate}</td>
                <td><span class="badge-status success">Indexed</span></td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-action" onclick="viewDocumentContext('${doc.document_id}', '${escapeHtml(doc.title)}')" title="View Vector Details"><i class="fa-solid fa-code"></i></button>
                        ${deleteButton}
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

async function viewDocumentContext(docId, docTitle) {
    try {
        const data = await apiRequest(`/rag/context/${docId}`);
        showToast(`Parsed: ${data.chunks_count} semantic vectors found!`, "info");
        
        
        const previewText = escapeHtml(data.text_preview);
        const overlay = document.createElement("div");
        overlay.className = "modal";
        overlay.innerHTML = `
            <div class="modal-backdrop" onclick="this.parentElement.remove()"></div>
            <div class="modal-card">
                <div class="modal-header">
                    <h3><i class="fa-solid fa-code text-indigo"></i> Ingested Node Context</h3>
                    <button class="btn-close-modal" onclick="this.closest('.modal').remove()">&times;</button>
                </div>
                <div style="font-size: 0.85rem; line-height: 1.4;">
                    <p style="margin-bottom: 12px;"><strong>Source Document:</strong> ${docTitle}</p>
                    <p style="margin-bottom: 12px;"><strong>Total Indexed vectors:</strong> ${data.chunks_count} chunks</p>
                    <div style="background: rgba(0,0,0,0.2); border: 1px solid var(--border-light); padding: 15px; border-radius: 8px; font-family: monospace; white-space: pre-wrap; max-height: 250px; overflow-y: auto;">
                        ${previewText}
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    } catch (e) {
        showToast("Error retrieving chunk metrics.", "error");
    }
}

async function handleDeleteDocument(docId) {
    if (!confirm("Are you sure you want to permanently delete this document and purge all corresponding vectors from Qdrant?")) {
        return;
    }
    
    try {
        const result = await apiRequest(`/documents/${docId}`, "DELETE");
        showToast(result.message || "Document successfully deleted.");
        fetchDocuments();
        loadDashboardOverview();
    } catch (error) {
        showToast(error.message || "Failed to delete document.", "error");
    }
}

// Semantic Search & Chat

async function submitRAGQuery(query = "") {
    if (!query.strip) query = query.trim();
    if (!query) return;
    
    
    appendChatBubble(query, "user");
    chatQueryInput.value = "";
    
    
    const botBubble = document.createElement("div");
    botBubble.className = "chat-bubble bot";
    botBubble.innerHTML = `
        <div class="bubble-content">
            <p><i class="fa-solid fa-spinner fa-spin"></i> Audit Copilot is calculating vectors, executing reranking, and formulating response...</p>
        </div>
    `;
    chatMessagesLog.appendChild(botBubble);
    chatMessagesLog.scrollTop = chatMessagesLog.scrollHeight;
    
    try {
        const result = await apiRequest("/rag/search", "POST", { query });
        
        
        botBubble.remove();
        appendChatBubble(result.answer, "bot");
        
        
        renderSourcedEvidence(result.chunks);
        
    } catch (error) {
        botBubble.remove();
        appendChatBubble(`Apologies, I encountered an operational error connecting to LLM nodes: ${error.message}`, "bot");
        showToast("AI Chat failed.", "error");
    }
}

function appendChatBubble(text, sender) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}`;
    
    
    const formattedText = text
        .replace(/\n\n/g, "</p><p>")
        .replace(/\[\d+\]/g, match => `<strong class="text-indigo">${match}</strong>`); // Highlight citations
        
    bubble.innerHTML = `
        <div class="bubble-content">
            <p>${formattedText}</p>
        </div>
    `;
    
    chatMessagesLog.appendChild(bubble);
    chatMessagesLog.scrollTop = chatMessagesLog.scrollHeight;
}

function renderSourcedEvidence(chunks) {
    if (chunks.length === 0) {
        sourcesContainer.classList.add("hidden");
        return;
    }
    
    sourcesContainer.classList.remove("hidden");
    sourceChunksGrid.innerHTML = chunks.map((c, idx) => {
        
        const scorePercentage = Math.round(c.score * 100);
        return `
            <div class="chunk-evidence-card">
                <div class="chunk-card-header">
                    <h5>[${idx + 1}] ${c.title}</h5>
                    <span class="chunk-score">${scorePercentage}% Relevance</span>
                </div>
                <p class="chunk-body-p">"${escapeHtml(c.text)}"</p>
                <div class="chunk-card-footer">
                    <span>Company: ${c.company_name}</span>
                    <span>Type: ${c.document_type}</span>
                </div>
            </div>
        `;
    }).join("");
}

//Navigation

navLinks.forEach(link => {
    link.addEventListener("click", (e) => {
        e.preventDefault();
        const targetPanel = link.getAttribute("data-target");
        
        
        navLinks.forEach(l => l.classList.remove("active"));
        link.classList.add("active");
        
        
        contentPanels.forEach(panel => {
            if (panel.id === targetPanel) {
                panel.classList.remove("hidden");
            } else {
                panel.classList.add("hidden");
            }
        });
        
        
        if (targetPanel === "panel-home") {
            panelTitle.innerText = "Overview Dashboard";
            panelSubtitle.innerText = "Comprehensive financial tracking and RAG retrieval hub.";
            loadDashboardOverview();
        } else if (targetPanel === "panel-documents") {
            panelTitle.innerText = "Document Library";
            panelSubtitle.innerText = "Audit and upload organization spreadsheets, reports, and contracts.";
            fetchDocuments();
        } else if (targetPanel === "panel-semantic-chat") {
            panelTitle.innerText = "Semantic Q&A Analytics";
            panelSubtitle.innerText = "Query financial datasets using cognitive vector AI.";
        } else if (targetPanel === "panel-rbac") {
            panelTitle.innerText = "Role Administration Dashboard";
            panelSubtitle.innerText = "Modify security roles and govern user access parameters.";
        }
    });
});

// Auth Tabs toggling

authTabs.forEach(tab => {
    tab.addEventListener("click", () => {
        authTabs.forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        
        if (tab.id === "tab-login") {
            loginForm.classList.remove("hidden");
            registerForm.classList.add("hidden");
            authSwitchText.innerText = "Don't have an account? Switch tab above.";
        } else {
            loginForm.classList.add("hidden");
            registerForm.classList.remove("hidden");
            authSwitchText.innerText = "Already registered? Switch tab above.";
        }
    });
});

// Forms Event Handlers

loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;
    
    try {
        const data = await apiRequest("/auth/login", "POST", { username, password, email: "login@temp.com", company_name: "temp" });
        token = data.access_token;
        localStorage.setItem("token", token);
        showToast("Log in successful. Hydrating session...");
        await initSession();
    } catch (err) {
        showToast(err.message || "Invalid username or password.", "error");
    }
});

registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("reg-username").value;
    const email = document.getElementById("reg-email").value;
    const company_name = document.getElementById("reg-company").value;
    const password = document.getElementById("reg-password").value;
    
    try {
        await apiRequest("/auth/register", "POST", { username, email, company_name, password });
        showToast("Registration successful! Switching tab to login...", "success");
        document.getElementById("tab-login").click();
    } catch (err) {
        showToast(err.message || "Registration failed.", "error");
    }
});

btnLogout.addEventListener("click", handleLogout);


btnFilterSearch.addEventListener("click", () => {
    const title = docFilterTitle.value;
    const company = docFilterCompany.value;
    const type = docFilterType.value;
    fetchDocuments(title, company, type);
});


btnTriggerUploadModal.addEventListener("click", () => uploadModal.classList.remove("hidden"));
btnCloseUploadModal.addEventListener("click", () => uploadModal.classList.add("hidden"));
btnCancelUpload.addEventListener("click", () => uploadModal.classList.add("hidden"));

uploadDocumentForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const title = document.getElementById("upload-title").value;
    const company_name = document.getElementById("upload-company").value;
    const document_type = document.getElementById("upload-type").value;
    const fileInput = document.getElementById("upload-file");
    
    if (fileInput.files.length === 0) {
        showToast("Please select a plain text report to upload.", "error");
        return;
    }
    
    const formData = new FormData();
    formData.append("title", title);
    formData.append("company_name", company_name);
    formData.append("document_type", document_type);
    formData.append("file", fileInput.files[0]);
    
    try {
        showToast("Uploading document and compiling semantic chunks...", "info");
        uploadModal.classList.add("hidden");
        
        await apiRequest("/documents/upload", "POST", formData, true);
        
        showToast("Document successfully processed and indexed into Qdrant!");
        uploadDocumentForm.reset();
        fetchDocuments();
        loadDashboardOverview();
    } catch (error) {
        showToast(error.message || "Upload failed.", "error");
    }
});


chatQueryForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const query = chatQueryInput.value;
    submitRAGQuery(query);
});
sampleQueryBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        chatQueryInput.value = btn.innerText;
        chatQueryInput.focus();
    });
});

// RBAC Role Assignment
rbacAssignForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const userId = parseInt(rbacUserId.value);
    const roleName = rbacRoleName.value;
    
    try {
        const result = await apiRequest("/users/assign-role", "POST", { user_id: userId, role_name: roleName });
        showToast(result.message || "Role assigned successfully.");
        rbacAssignForm.reset();
    } catch (err) {
        showToast(err.message || "Role assignment failed.", "error");
    }
});

window.addEventListener("DOMContentLoaded", () => {
    initSession();
});
