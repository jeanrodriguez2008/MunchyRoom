/* MunchyRoom · JavaScript de interfaz (sin dependencias, Alpine.js complementario). */
(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /* Mensajes flash: autocierre                                          */
  /* ------------------------------------------------------------------ */
  function autoDismissFlashes() {
    document.querySelectorAll("[data-flash]").forEach(function (el) {
      window.setTimeout(function () {
        el.style.transition = "opacity 300ms ease, transform 300ms ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-6px)";
        window.setTimeout(function () { el.remove(); }, 320);
      }, 8000);
    });
  }

  /* ------------------------------------------------------------------ */
  /* Confirmaciones en formularios con data-confirm                      */
  /* ------------------------------------------------------------------ */
  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });

  /* ------------------------------------------------------------------ */
  /* PWA: registro del service worker                                    */
  /* ------------------------------------------------------------------ */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      var secure = window.location.protocol === "https:" || window.location.hostname === "localhost";
      if (!secure) return;
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {
        /* Silencioso: la app funciona igual sin soporte offline. */
      });
    });
  }

  /* ------------------------------------------------------------------ */
  /* Formulario de nueva reserva (Alpine.js)                             */
  /* ------------------------------------------------------------------ */
  window.reservationForm = function (config) {
    config = config || {};
    return {
      roomId: String(config.roomId || ""),
      date: config.date || "",
      start: config.start || "",
      duration: Number(config.duration || 60),
      expected: Number(config.expected || 1),
      rooms: config.rooms || [],
      selected: (config.selected || []).map(String),
      query: "",
      checking: false,
      submitting: false,
      checkResult: null,
      _timer: null,

      get room() {
        var current = this;
        return this.rooms.find(function (r) { return String(r.id) === String(current.roomId); }) || null;
      },

      get endLabel() {
        if (!this.start) return "";
        var parts = this.start.split(":");
        var hours = Number(parts[0]);
        var minutes = Number(parts[1]);
        if (isNaN(hours) || isNaN(minutes)) return "";
        var total = hours * 60 + minutes + Number(this.duration || 0);
        if (total >= 1440) return "Fuera del día";
        var h = Math.floor(total / 60) % 24;
        var m = total % 60;
        var suffix = h >= 12 ? "PM" : "AM";
        var display = h % 12 || 12;
        return display + ":" + String(m).padStart(2, "0") + " " + suffix;
      },

      init: function () {
        var self = this;
        ["roomId", "date", "start", "duration"].forEach(function (property) {
          self.$watch(property, function () { self.check(); });
        });
        this.check();
      },

      check: function () {
        var self = this;
        if (!this.roomId || !this.date || !this.start || !this.duration) {
          this.checkResult = null;
          return;
        }
        window.clearTimeout(this._timer);
        this.checking = true;
        this._timer = window.setTimeout(function () {
          var params = new URLSearchParams({
            room_id: self.roomId,
            date: self.date,
            start: self.start,
            duration: String(self.duration)
          });
          fetch("/api/availability?" + params.toString(), {
            headers: { "Accept": "application/json" },
            credentials: "same-origin"
          })
            .then(function (response) { return response.json(); })
            .then(function (data) {
              data.pending = data.pending || [];
              self.checkResult = data;
            })
            .catch(function () {
              self.checkResult = {
                ok: false,
                hard_conflict: true,
                pending: [],
                message: "No se pudo verificar la disponibilidad. Revisa tu conexión."
              };
            })
            .finally(function () { self.checking = false; });
        }, 350);
      },

      syncExpected: function () {
        if (Number(this.expected) < this.selected.length) {
          this.expected = this.selected.length;
        }
      }
    };
  };

  document.addEventListener("DOMContentLoaded", autoDismissFlashes);
})();
