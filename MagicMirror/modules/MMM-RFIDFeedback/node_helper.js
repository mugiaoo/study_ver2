const NodeHelper = require("node_helper");
const bodyParser = require("body-parser");
const express = require("express");

module.exports = NodeHelper.create({
  start: function () {
    this.expressApp.use(bodyParser.json());

    // PythonからのPOST受付
    this.expressApp.post("/feedback", (req, res) => {
      const message = req.body.message || "💄 化粧してえらい！！";
      this.sendSocketNotification("SHOW_FEEDBACK", message);
      res.sendStatus(200);
    });

    console.log("MMM-RFIDFeedback helper started.");
  }
});
