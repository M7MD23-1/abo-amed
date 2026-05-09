const form = document.getElementById("builderForm");
const statusMessage = document.getElementById("statusMessage");
const resultMeta = document.getElementById("resultMeta");
const componentsList = document.getElementById("componentsList");
const componentsTableBody = document.getElementById("componentsTableBody");
const searchButton = document.getElementById("searchButton");
const spinner = searchButton.querySelector(".spinner");
const buttonText = searchButton.querySelector(".btn-text");
const currencySelect = document.getElementById("currency");
const languageSelect = document.getElementById("language");
const subtotalValue = document.getElementById("subtotalValue");
const totalValue = document.getElementById("totalValue");

const labels = {
    en: {
        pageTitle: "AI-Based PC Builder",
        subtitle: "Smart component selection using BFS, DFS, UCS, and A*",
        budget: "Budget",
        purpose: "Purpose",
        algorithm: "Algorithm",
        selectPurpose: "Select purpose",
        selectAlgorithm: "Select algorithm",
        search: "Search Build",
        searching: "Searching for best valid build...",
        result: "Result",
        totalPrice: "Total Price",
        totalOnly: "Total",
        explored: "Explored States",
        searchTime: "Search Time (ms)",
        steps: "Steps to Goal",
        compatibility: "Compatibility",
        component: "Component",
        selected: "Selected Item",
        price: "Price",
        subtotal: "Parts Total",
        pathDepth: "Path Depth",
        builds: "Builds Returned",
        notSelected: "Not selected",
        statusReady: "Fill the form and run search.",
        statusSearching: "Searching for best valid build...",
        statusSuccess: "Build found successfully.",
        currency: "Currency",
        language: "Language",
        purposes: {
            Gaming: "Gaming",
            "Office / General Use": "Office",
            "Content Creation": "Content Creation",
            "AI / ML Workstation": "ML Workstation",
            "Budget Build": "Budget Build",
            "High-End Build": "High-End Build",
        },
    },
    ar: {
        pageTitle: "مساعد تجميع الحاسوب الذكي",
        subtitle: "اختيار ذكي للقطع باستخدام BFS و DFS و UCS و A*",
        budget: "الميزانية",
        purpose: "الغرض",
        algorithm: "الخوارزمية",
        selectPurpose: "اختر الغرض",
        selectAlgorithm: "اختر الخوارزمية",
        search: "ابحث عن أفضل تجميعة",
        searching: "جاري البحث عن أفضل تجميعة...",
        result: "النتيجة",
        totalPrice: "السعر الإجمالي",
        totalOnly: "الإجمالي",
        explored: "الحالات المستكشفة",
        searchTime: "وقت البحث (مللي ثانية)",
        steps: "عدد الخطوات للوصول للهدف",
        compatibility: "التوافق",
        component: "القطعة",
        selected: "القطعة المختارة",
        price: "السعر",
        subtotal: "إجمالي القطع",
        pathDepth: "عمق المسار",
        builds: "عدد التجميعات المعروضة",
        notSelected: "غير محدد",
        statusReady: "املأ النموذج ثم ابدأ البحث.",
        statusSearching: "جاري البحث عن أفضل تجميعة...",
        statusSuccess: "تم العثور على تجميعة بنجاح.",
        currency: "العملة",
        language: "اللغة",
        purposes: {
            Gaming: "ألعاب",
            "Office / General Use": "مكتبي",
            "Content Creation": "صناعة محتوى",
            "AI / ML Workstation": "محطة تعلم آلي",
            "Budget Build": "تجميعة اقتصادية",
            "High-End Build": "تجميعة عالية الأداء",
        },
    },
};

const currencyRates = {
    USD: 1,
    OMR: 0.385,
    SAR: 3.75,
    AED: 3.67,
    EUR: 0.92,
};

const componentIcons = {
    cpu: "/static/images/cpu.svg",
    motherboard: "/static/images/motherboard.svg",
    ram: "/static/images/ram.svg",
    storage: "/static/images/storage.svg",
    gpu: "/static/images/gpu.svg",
    psu: "/static/images/psu.svg",
    default: "/static/images/default.svg",
};

let currentResult = null;

function getActiveLanguage() {
    return languageSelect.value === "ar" ? labels.ar : labels.en;
}

function getCurrencyConfig() {
    const code = currencySelect.value;
    return { code, rate: currencyRates[code] || 1 };
}

function formatPrice(usdValue) {
    const { code, rate } = getCurrencyConfig();
    const converted = Number(usdValue || 0) * rate;
    return `${converted.toFixed(2)} ${code}`;
}

function budgetToUsd() {
    const budgetInput = Number(document.getElementById("budget").value || 0);
    const { rate } = getCurrencyConfig();
    if (rate <= 0) {
        return 0;
    }
    return budgetInput / rate;
}

function setStatus(message, type = "") {
    statusMessage.textContent = message;
    statusMessage.className = "status";
    if (type) {
        statusMessage.classList.add(type);
    }
}

function applyLanguage() {
    const t = getActiveLanguage();
    const isArabic = languageSelect.value === "ar";
    document.documentElement.lang = isArabic ? "ar" : "en";
    document.documentElement.dir = isArabic ? "rtl" : "ltr";
    document.title = t.pageTitle;

    document.getElementById("titleText").textContent = t.pageTitle;
    document.getElementById("subtitleText").textContent = t.subtitle;

    document.getElementById("budgetLabel").textContent = t.budget;
    document.getElementById("purposeLabel").textContent = t.purpose;
    document.getElementById("algorithmLabel").textContent = t.algorithm;
    document.getElementById("resultHeading").textContent = t.result;
    document.getElementById("searchButtonText").textContent = t.search;
    document.getElementById("thComponent").textContent = t.component;
    document.getElementById("thSelected").textContent = t.selected;
    document.getElementById("thPrice").textContent = t.price;
    document.getElementById("subtotalLabel").textContent = t.subtotal;
    document.getElementById("totalLabel").textContent = t.totalOnly;
    document.querySelector("label[for='currency']").textContent = t.currency;
    document.querySelector("label[for='language']").textContent = t.language;
    document.getElementById("budget").placeholder = t.budget;

    const purposeSelect = document.getElementById("purpose");
    const purposePlaceholder = purposeSelect.querySelector("option[value='']");
    if (purposePlaceholder) {
        purposePlaceholder.textContent = t.selectPurpose;
    }
    Array.from(purposeSelect.options).forEach((option) => {
        if (option.value && t.purposes[option.value]) {
            option.textContent = t.purposes[option.value];
        }
    });

    const algorithmSelect = document.getElementById("algorithm");
    const algorithmPlaceholder = algorithmSelect.querySelector("option[value='']");
    if (algorithmPlaceholder) {
        algorithmPlaceholder.textContent = t.selectAlgorithm;
    }

    const currencyOptionLabels = {
        en: {
            USD: "USD - US Dollar",
            OMR: "OMR - Omani Rial",
            SAR: "SAR - Saudi Riyal",
            AED: "AED - UAE Dirham",
            EUR: "EUR - Euro",
        },
        ar: {
            USD: "USD - دولار أمريكي",
            OMR: "OMR - ريال عماني",
            SAR: "SAR - ريال سعودي",
            AED: "AED - درهم إماراتي",
            EUR: "EUR - يورو",
        },
    };
    Array.from(currencySelect.options).forEach((option) => {
        const labelMap = isArabic ? currencyOptionLabels.ar : currencyOptionLabels.en;
        if (labelMap[option.value]) {
            option.textContent = labelMap[option.value];
        }
    });

    const languageOptionLabels = isArabic
        ? { en: "الإنجليزية", ar: "العربية" }
        : { en: "English", ar: "Arabic" };
    Array.from(languageSelect.options).forEach((option) => {
        if (languageOptionLabels[option.value]) {
            option.textContent = languageOptionLabels[option.value];
        }
    });
}

function translateServerText(text) {
    if (languageSelect.value !== "ar" || !text) {
        return text;
    }
    const map = {
        "All compatibility constraints satisfied.": "تم استيفاء جميع قيود التوافق.",
        "Compatible so far.": "متوافق حتى الآن.",
        "Build found successfully.": labels.ar.statusSuccess,
        "Searching for best valid build...": labels.ar.statusSearching,
        "No valid build found.": "لم يتم العثور على تجميعة مناسبة.",
    };
    return map[text] || text;
}

function showMeta(result) {
    const t = getActiveLanguage();
    const metaItems = [
        { label: t.algorithm, value: result.algorithm || "-" },
        { label: t.totalPrice, value: formatPrice(result.total_price || 0) },
        { label: t.explored, value: result.explored_states ?? "-" },
        { label: t.searchTime, value: result.search_time_ms ?? "-" },
        { label: t.pathDepth, value: result.path_depth ?? "-" },
        { label: t.steps, value: result.steps_to_goal ?? "-" },
        { label: t.builds, value: result.results_count ?? "-" },
        { label: t.compatibility, value: translateServerText(result.compatibility_status || "-") },
    ];

    resultMeta.innerHTML = metaItems
        .map(
            (item) => `
            <div class="meta-item">
                <strong>${item.label}</strong>
                <div>${item.value}</div>
            </div>
        `
        )
        .join("");
    resultMeta.classList.remove("hidden");
}

function showComponents(selectedComponents) {
    const t = getActiveLanguage();
    const order = ["cpu", "motherboard", "ram", "storage", "gpu", "psu"];
    let subtotalUsd = 0;

    componentsTableBody.innerHTML = order
        .map((key) => {
            const item = selectedComponents[key];
            const iconPath = componentIcons[key] || componentIcons.default;

            if (!item) {
                return `
                    <tr>
                        <td>
                            <div class="component-cell">
                                <img class="component-icon" src="${iconPath}" onerror="this.src='${componentIcons.default}'" alt="${key}">
                                <span>${key.toUpperCase()}</span>
                            </div>
                        </td>
                        <td>${t.notSelected}</td>
                        <td>-</td>
                    </tr>
                `;
            }

            subtotalUsd += Number(item.price || 0);
            return `
                <tr>
                    <td>
                        <div class="component-cell">
                            <img class="component-icon" src="${iconPath}" onerror="this.src='${componentIcons.default}'" alt="${key}">
                            <span>${key.toUpperCase()}</span>
                        </div>
                    </td>
                    <td>${item.name}</td>
                    <td>${formatPrice(item.price)}</td>
                </tr>
            `;
        })
        .join("");

    subtotalValue.textContent = formatPrice(subtotalUsd);
    const totalFromResult = Number(currentResult?.total_price || subtotalUsd);
    totalValue.textContent = formatPrice(totalFromResult);
    componentsList.classList.remove("hidden");
}

function refreshResultView() {
    if (!currentResult || !currentResult.success) {
        return;
    }
    showMeta(currentResult);
    showComponents(currentResult.selected_components);
}

function setLoading(isLoading) {
    const t = getActiveLanguage();
    searchButton.disabled = isLoading;
    spinner.classList.toggle("hidden", !isLoading);
    buttonText.textContent = isLoading ? t.searching : t.search;
}

currencySelect.addEventListener("change", () => {
    refreshResultView();
});

languageSelect.addEventListener("change", () => {
    applyLanguage();
    if (!currentResult) {
        setStatus(getActiveLanguage().statusReady);
    } else {
        refreshResultView();
    }
});

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const t = getActiveLanguage();
    const budgetUsd = budgetToUsd();
    const purpose = document.getElementById("purpose").value;
    const algorithm = document.getElementById("algorithm").value;

    resultMeta.classList.add("hidden");
    componentsList.classList.add("hidden");
    componentsTableBody.innerHTML = "";
    currentResult = null;
    setStatus(t.statusSearching);
    setLoading(true);

    try {
        const response = await fetch("/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ budget: budgetUsd, purpose, algorithm }),
        });

        const result = await response.json();
        if (!response.ok || !result.success) {
            setStatus(translateServerText(result.message || "No valid build found."), "error");
            showMeta(result);
            return;
        }

        currentResult = result;
        setStatus(t.statusSuccess, "success");
        showMeta(result);
        showComponents(result.selected_components);
    } catch (error) {
        setStatus(`Request failed: ${error.message}`, "error");
    } finally {
        setLoading(false);
    }
});

applyLanguage();
setStatus(labels.en.statusReady);
