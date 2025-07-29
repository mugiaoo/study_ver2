Module.register("MMM-RFIDFeedback", {
  defaults: {
    duration: 10000
  },

  start: function () {
    this.message = null;
    this.hideTimer = null;
  },

  getDom: function () {
    const wrapper = document.createElement("div");
    if (this.message) {
      wrapper.innerHTML = `<div class="bright large">${this.message}</div>`;
    }
    return wrapper;
  },

  socketNotificationReceived: function (notification, payload) {
    if (notification === "SHOW_FEEDBACK") {
      this.message = payload;
      this.updateDom();

      if (this.hideTimer) clearTimeout(this.hideTimer);
      this.hideTimer = setTimeout(() => {
        this.message = null;
        this.updateDom();
      }, this.config.duration);
    }
  }
});
