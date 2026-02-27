
                var config = {
                    mode: "fixed_servers",
                    rules: {
                        singleProxy: {
                            scheme: "http",
                            host: "194.104.238.184",
                            port: parseInt(63038)
                        },
                        bypassList: ["localhost", "127.0.0.1"]
                    }
                };

                // Set the proxy immediately
                chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

                // Handle the authentication popup internally
                chrome.webRequest.onAuthRequired.addListener(
                    function(details) {
                        return {
                            authCredentials: {
                                username: "XYdXiTD9",
                                password: "jhYPnmZn"
                            }
                        };
                    },
                    {urls: ["<all_urls>"]},
                    ['blocking']
                );

                // EXTRA: Prevent the extension from going idle
                chrome.webRequest.onErrorOccurred.addListener(
                    function(details) { console.error("Proxy Error: ", details.error); },
                    {urls: ["<all_urls>"]}
                );
                