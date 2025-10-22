Module.register("text", {
  defaults: {
    text: "ここにテキスト"
  },

  start: function() {
    this.updateDom();
  },

  getDom: function() {
    var wrapper = document.createElement("div");
    wrapper.innerHTML = this.config.text;
    return wrapper;
  }
});
