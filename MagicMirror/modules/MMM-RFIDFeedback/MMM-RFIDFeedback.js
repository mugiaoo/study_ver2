Module.register("MMM-FeedbackDisplay", {
  defaults: {
    duration: 10000,
    endpoint: "http://localhost:8000/feedback",
    updateInterval: 10000  // デフォルト更新間隔
  },

  start: function () {
    this.message = null;
    this.hideTimer = null;

    this.getFeedback();  // 初回実行
    setInterval(() => {
      this.getFeedback();  // 一定間隔で更新
    }, this.config.updateInterval);
  },

  getDom: function () {
    const wrapper = document.createElement("div");
    if (this.message) {
      wrapper.innerHTML = `<div class="bright large">${this.message}</div>`;
    }
    return wrapper;
  },

  getFeedback: function () {
    fetch(this.config.endpoint)
      .then(response => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();  // Flask からは JSON が返る前提
      })
      .then(data => {
        if (data && data.message) {
          this.message = data.message;
          this.updateDom();

          if (this.hideTimer) clearTimeout(this.hideTimer);
          this.hideTimer = setTimeout(() => {
            this.message = null;
            this.updateDom();
          }, this.config.duration);
        }
      })
      .catch(error => {
        console.error("[送信エラー] フィードバック取得中に例外発生:", error);
      });
  }
});
