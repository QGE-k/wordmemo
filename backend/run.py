from app import app

if __name__ == '__main__':
    # 启动Flask开发服务器，监听所有网络接口的5000端口
    app.run(host='0.0.0.0', port=5000, debug=True)
