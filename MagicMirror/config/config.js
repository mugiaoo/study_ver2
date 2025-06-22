let config = {
  address: "localhost",
  port: 8080,
  basePath: "/",
  ipWhitelist: [],  // ローカルからだけアクセス可能

  modules: [
    {
      module: "clock",
      position: "top_left",
      config: {
        displayType: "digital",
        // ここで24時間表示など細かく設定可能
      }
    },
    {
      module: "text",
      position: "top_right",
      config: {
        text: "こんにちは、スマートミラーへようこそ！",
        // もっとカスタムしたければmoduleのjsやcssを編集も可能
      }
    }
  ]
};

if (typeof module !== "undefined") {module.exports = config;}
