Module.register("text", {
  defaults: {
    text: "こんにちは！",
    updateInterval: 60000
  },

  start() {
    this.message = this.config.text;
    if (this.config.updateInterval > 0) {
      setInterval(() => {
        this.updateDom();
      }, this.config.updateInterval);
    }
  },

  getDom() {
    const wrapper = document.createElement("div");
    wrapper.className = "text-content";
    wrapper.innerText = this.message;
    return wrapper;
  },

  getStyles() {
    return ["text.css"];
  }
});
