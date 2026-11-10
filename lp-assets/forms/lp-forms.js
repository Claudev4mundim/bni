/*
 * Envio dos formulários das LPs sem o WordPress.
 *
 * Os formulários continuam com o HTML e o visual originais (WPForms/Elementor);
 * tools/localize_forms.py marca cada um com data-lp-form="<chave>" e desliga o
 * envio pelo WordPress. Aqui o envio vai para a função /api/enviar do projeto
 * "bni", que repassa os dados para os webhooks originais.
 *
 * Depois de enviar, dispara os mesmos eventos jQuery que os plugins disparavam
 * (wpformsAjaxSubmitSuccess / submit_success), para não quebrar tags que
 * dependam deles.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var ENDPOINT = (script && script.getAttribute("data-endpoint")) || "https://lps-bni.vercel.app/api/enviar";
  var GENERIC_ERROR = "Não foi possível enviar agora. Tente novamente em instantes.";

  function kindOf(key) {
    return key.indexOf("wpforms:") === 0 ? "wpforms" : "elementor";
  }

  function clearErrors(form) {
    var old = form.querySelectorAll("[data-lp-error]");
    for (var i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var marked = form.querySelectorAll(".wpforms-error, .elementor-error");
    for (var j = 0; j < marked.length; j++) {
      if (marked[j].tagName !== "EM") marked[j].classList.remove("wpforms-error", "elementor-error");
    }
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    e.className = cls;
    e.setAttribute("role", "alert");
    e.setAttribute("data-lp-error", "");
    e.textContent = text;
    return e;
  }

  function showFieldError(form, kind, id, msg) {
    var input;
    if (kind === "wpforms") {
      input = form.querySelector('[name="wpforms[fields][' + id + ']"], [name="wpforms[fields][' + id + '][]"], [name="wpf-temp-wpforms[fields][' + id + ']"]');
      if (!input) return false;
      input.classList.add("wpforms-error");
      var holder = input.closest(".wpforms-field") || input.parentNode;
      holder.appendChild(el("em", "wpforms-error", msg));
    } else {
      input = form.querySelector('[name="form_fields[' + id + ']"], [name="form_fields[' + id + '][]"]');
      if (!input) return false;
      var group = input.closest(".elementor-field-group") || input.parentNode;
      group.classList.add("elementor-error");
      group.appendChild(el("span", "elementor-message elementor-message-danger elementor-help-inline elementor-form-help-inline", msg));
    }
    return true;
  }

  function showMessage(form, kind, msg, ok) {
    if (kind === "wpforms") {
      var box = el("div", "wpforms-error-container", "");
      var p = document.createElement("p");
      p.textContent = msg;
      box.appendChild(p);
      form.insertBefore(box, form.firstChild);
    } else {
      form.appendChild(el("div", "elementor-message " + (ok ? "elementor-message-success" : "elementor-message-danger"), msg));
    }
  }

  function setBusy(form, kind, busy) {
    form.__lpBusy = busy;
    form.setAttribute("aria-busy", busy ? "true" : "false");
    var btn = form.querySelector('[type="submit"]');
    if (btn) {
      btn.disabled = busy;
      if (kind === "wpforms") {
        var alt = btn.getAttribute("data-alt-text");
        if (busy && alt) {
          btn.setAttribute("data-lp-text", btn.textContent);
          btn.textContent = alt;
        } else if (!busy && btn.hasAttribute("data-lp-text")) {
          btn.textContent = btn.getAttribute("data-lp-text");
        }
        var spin = form.querySelector(".wpforms-submit-spinner");
        if (spin) spin.style.display = busy ? "inline-block" : "none";
      }
    }
    if (kind === "elementor") form.style.opacity = busy ? "0.45" : "";
  }

  function trigger(form, name, data) {
    var $ = window.jQuery;
    if ($) {
      try {
        $(form).trigger(name, [data]);
      } catch (e) { /* tags de terceiros não podem quebrar o envio */ }
    }
  }

  function setHidden(form, name, value) {
    var input = form.querySelector('input[name="' + name + '"]');
    if (input) input.value = value;
  }

  function submit(form) {
    var key = form.getAttribute("data-lp-form");
    var kind = kindOf(key);
    if (form.__lpBusy) return;
    clearErrors(form);
    if (typeof form.reportValidity === "function" && !form.reportValidity()) return;

    setHidden(form, "page_url", location.href);
    setHidden(form, "url_referer", document.referrer);
    var entries = [];
    new FormData(form).forEach(function (value, name) {
      if (typeof value === "string") entries.push([name, value]);
    });

    setBusy(form, kind, true);
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ form: key, entries: entries, page_url: location.href, url_referer: document.referrer }),
    })
      .then(function (r) {
        return r.json().catch(function () { return { ok: false }; });
      })
      .then(function (res) {
        if (!res || !res.ok) {
          setBusy(form, kind, false);
          var shown = false;
          if (res && res.errors) {
            for (var id in res.errors) shown = showFieldError(form, kind, id, res.errors[id]) || shown;
          }
          if (!shown || kind === "elementor") showMessage(form, kind, (res && res.message) || GENERIC_ERROR, false);
          return;
        }
        if (kind === "wpforms") {
          trigger(form, "wpformsAjaxSubmitSuccess", { success: true, data: res });
          if (res.redirect) {
            location.href = new URL(res.redirect, location.href).href;
            return;
          }
          var container = form.closest(".wpforms-container") || form.parentNode;
          var conf = document.createElement("div");
          conf.className = "wpforms-confirmation-container-full wpforms-confirmation-scroll";
          conf.setAttribute("role", "alert");
          conf.innerHTML = res.message || "";
          container.innerHTML = "";
          container.appendChild(conf);
          conf.scrollIntoView({ behavior: "smooth", block: "center" });
        } else {
          setBusy(form, kind, false);
          form.reset();
          if (res.message) showMessage(form, kind, res.message, true);
          trigger(form, "submit_success", res);
          if (res.redirect) location.href = new URL(res.redirect, location.href).href;
        }
      })
      .catch(function () {
        setBusy(form, kind, false);
        showMessage(form, kind, GENERIC_ERROR, false);
      });
  }

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (!form || !form.getAttribute || !form.getAttribute("data-lp-form")) return;
    ev.preventDefault();
    submit(form);
  });
})();
