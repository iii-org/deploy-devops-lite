from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    # 使用template資料夾內的home.html當作首頁
    return render_template("home.html")
    
@app.route("/about")
def about():
    # 使用template資料夾內的about.html當作首頁
    return render_template("about.html")
    
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
