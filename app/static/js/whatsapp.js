/* MunchyRoom · Cola guiada de convocatoria por WhatsApp. */
(function () {
  "use strict";

  window.whatsappQueue = function (participants, reservationId, genericMessage, shareText) {
    return {
      participants: (participants || []).map(function (p) {
        p.notified = Boolean(p.notified);
        return p;
      }),
      reservationId: reservationId,
      genericMessage: genericMessage || "",
      shareText: shareText || "",
      copied: "",
      error: "",

      get sentCount() {
        return this.participants.filter(function (p) { return p.notified; }).length;
      },

      get progress() {
        if (!this.participants.length) return 0;
        return Math.round((this.sentCount / this.participants.length) * 100);
      },

      get nextPending() {
        return this.participants.find(function (p) { return !p.notified && p.link; }) || null;
      },

      openNext: function () {
        var participant = this.nextPending;
        if (!participant) return;
        var win = window.open(participant.link, "_blank", "noopener");
        if (!win) {
          this.error = "El navegador bloqueó la ventana. Permite las ventanas emergentes para este sitio e inténtalo de nuevo.";
          return;
        }
        this.error = "";
        this.mark(participant, true);
      },

      mark: function (participant, notified) {
        var self = this;
        var previous = participant.notified;
        participant.notified = notified;
        this.error = "";

        var body = new URLSearchParams();
        body.set("notified", notified ? "true" : "false");

        fetch("/reservations/" + this.reservationId + "/whatsapp/" + participant.row_id + "/mark", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "fetch",
            "Accept": "application/json"
          },
          credentials: "same-origin",
          body: body.toString()
        })
          .then(function (response) { return response.json(); })
          .then(function (data) {
            if (!data.ok) {
              participant.notified = previous;
              self.error = data.message || "No se pudo guardar el estado del participante.";
            }
          })
          .catch(function () {
            participant.notified = previous;
            self.error = "No se pudo guardar el estado. Revisa tu conexión e inténtalo de nuevo.";
          });
      },

      copy: function (text, kind) {
        var self = this;
        if (!text) return;

        function done() {
          self.copied = kind;
          window.setTimeout(function () {
            if (self.copied === kind) self.copied = "";
          }, 2500);
        }

        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(done).catch(function () { self.fallbackCopy(text, done); });
        } else {
          this.fallbackCopy(text, done);
        }
      },

      fallbackCopy: function (text, done) {
        var area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        try { document.execCommand("copy"); done(); } catch (error) {
          this.error = "No se pudo copiar automáticamente. Selecciona el texto y cópialo manualmente.";
        }
        document.body.removeChild(area);
      },

      copyNumbers: function () {
        var lines = this.participants.map(function (p) {
          return (p.phone || "sin teléfono") + " — " + p.name;
        });
        this.copy(lines.join("\n"), "numbers");
      }
    };
  };
})();
