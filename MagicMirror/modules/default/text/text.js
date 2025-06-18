Module.register("text", {
  defaults: {
    text: "ここに任意のテキストを入れてください",
    updateInterval: 60000
  },

  start: function() {
    this.text = this.config.text;
    var self = this;
    setInterval(function() {
      self.updateDom();
    }, this.config.updateInterval);
  },

  getDom: function() {
    var wrapper = document.createElement("div");
    wrapper.innerHTML = this.text;
    return wrapper;
  }
});
