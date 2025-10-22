Module.register("MMM-RFIDFeedback", {
  defaults: {
    duration: 10000,
    endpoint: "http://localhost:8000/feedback",
    updateInterval: 10000
  },

  start: function () {

    console.log("[MMM-RFIDFeedback] start() called");

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

//   socketNotificationReceived: function (notification, payload) {
//     if (notification === "SHOW_FEEDBACK") {
//       this.message = payload;
//       this.updateDom();

//       if (this.hideTimer) clearTimeout(this.hideTimer);
//       this.hideTimer = setTimeout(() => {
//         this.message = null;
//         this.updateDom();
//       }, this.config.duration);
//     }
//   },

  getFeedback: function () {
    fetch(this.config.endpoint)
      .then(response => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();
      })
      .then(data => {
        console.log("[getFeedback] 取得データ:", data);
        if (data && data.message) {
          this.message = data.message;
          console.log("[getFeedback] メッセージ更新:", this.message);
          this.updateDom();

          if (this.hideTimer) clearTimeout(this.hideTimer);
          this.hideTimer = setTimeout(() => {
            this.message = null;
            this.updateDom();
          }, this.config.duration);
        }
      })
      .catch(error => {
        console.error("[取得エラー] フィードバック取得中に例外発生:", error);
      });
  }
});
