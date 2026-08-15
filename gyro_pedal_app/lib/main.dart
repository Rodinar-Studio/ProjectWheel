import 'dart:async';
import 'dart:convert';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:sensors_plus/sensors_plus.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:flutter_background/flutter_background.dart';
import 'package:flutter_blue_classic/flutter_blue_classic.dart';

void main() {
  runApp(const GyroPedalApp());
}

class GyroPedalApp extends StatelessWidget {
  const GyroPedalApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Gyro Pedal Client',
      theme: ThemeData(
        brightness: Brightness.dark,
        primarySwatch: Colors.amber,
        scaffoldBackgroundColor: const Color(0xFF121212),
        cardColor: const Color(0xFF1E1E1E),
      ),
      home: const ConnectionScreen(),
    );
  }
}

class ConnectionScreen extends StatefulWidget {
  const ConnectionScreen({Key? key}) : super(key: key);

  @override
  State<ConnectionScreen> createState() => _ConnectionScreenState();
}

class _ConnectionScreenState extends State<ConnectionScreen> {
  final TextEditingController _ipController = TextEditingController(text: '192.168.1.100');
  final TextEditingController _portController = TextEditingController(text: '8000');
  String _connMode = 'wifi'; // 'wifi', 'usb', 'bluetooth'
  bool _isConnecting = false;

  final _blueClassic = FlutterBlueClassic();
  List<BluetoothDevice> _pairedDevices = [];
  String? _selectedDeviceAddress;
  bool _isBtLoading = false;

  @override
  void initState() {
    super.initState();
  }

  Future<void> _loadBluetoothDevices() async {
    setState(() {
      _isBtLoading = true;
    });
    try {
      final isEnabled = await _blueClassic.isEnabled;
      if (!isEnabled) {
        await _blueClassic.turnOn();
      }
      final devices = await _blueClassic.bondedDevices;
      setState(() {
        _pairedDevices = devices ?? [];
        if (_pairedDevices.isNotEmpty) {
          _selectedDeviceAddress = _pairedDevices.first.address;
        } else {
          _selectedDeviceAddress = null;
        }
        _isBtLoading = false;
      });
    } catch (e) {
      setState(() {
        _isBtLoading = false;
      });
      print("BT loading error: $e");
    }
  }

  void _connect() async {
    setState(() {
      _isConnecting = true;
    });

    if (_connMode == 'bluetooth') {
      if (_selectedDeviceAddress == null) {
        setState(() {
          _isConnecting = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Lütfen bir Bluetooth cihazı seçin.')),
        );
        return;
      }
      try {
        final connection = await _blueClassic.connect(_selectedDeviceAddress!);
        if (!mounted) return;
        setState(() {
          _isConnecting = false;
        });
        if (connection != null && connection.isConnected) {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => PedalAssignmentScreen(
                btConnection: connection,
                wsUrl: 'Bluetooth: $_selectedDeviceAddress',
              ),
            ),
          );
        } else {
          throw Exception("Bağlantı kurulamadı.");
        }
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _isConnecting = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Bluetooth Bağlantı Hatası: $e'),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    } else {
      final ip = _connMode == 'usb' ? '127.0.0.1' : _ipController.text.trim();
      final port = _portController.text.trim();
      final wsUrl = 'ws://$ip:$port/ws/pedal';

      try {
        final channel = WebSocketChannel.connect(Uri.parse(wsUrl));
        await channel.ready.timeout(const Duration(seconds: 4));
        
        if (!mounted) return;
        setState(() {
          _isConnecting = false;
        });

        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (context) => PedalAssignmentScreen(
              channel: channel,
              wsUrl: wsUrl,
            ),
          ),
        );
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _isConnecting = false;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Bağlantı hatası: $e\nLütfen backend sunucusunun açık ve aynı ağda olduğunu kontrol edin.'),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🚗 Gyro Pedal Client'),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Card(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            elevation: 8,
            child: Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    'Bağlantı Ayarları',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.amber),
                  ),
                  const SizedBox(height: 24),
                  
                  // Connection Mode Toggle
                  Row(
                    children: [
                      Expanded(
                        child: ChoiceChip(
                          label: const Center(child: Text('WiFi')),
                          selected: _connMode == 'wifi',
                          onSelected: (selected) {
                            if (selected) {
                              setState(() {
                                _connMode = 'wifi';
                              });
                            }
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: ChoiceChip(
                          label: const Center(child: Text('USB')),
                          selected: _connMode == 'usb',
                          onSelected: (selected) {
                            if (selected) {
                              setState(() {
                                _connMode = 'usb';
                              });
                            }
                          },
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: ChoiceChip(
                          label: const Center(child: Text('Bluetooth')),
                          selected: _connMode == 'bluetooth',
                          onSelected: (selected) {
                            if (selected) {
                              setState(() {
                                _connMode = 'bluetooth';
                              });
                              _loadBluetoothDevices();
                            }
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),

                  if (_connMode == 'wifi') ...[
                    TextField(
                      controller: _ipController,
                      decoration: const InputDecoration(
                        labelText: 'PC Yerel IP Adresi',
                        border: OutlineInputBorder(),
                        hintText: 'Örn: 192.168.3.100',
                      ),
                      keyboardType: TextInputType.text,
                    ),
                    const SizedBox(height: 16),
                  ],

                  if (_connMode != 'bluetooth') ...[
                    TextField(
                      controller: _portController,
                      decoration: const InputDecoration(
                        labelText: 'Port',
                        border: OutlineInputBorder(),
                      ),
                      keyboardType: TextInputType.number,
                      enabled: _connMode == 'wifi',
                    ),
                    const SizedBox(height: 24),
                  ],

                  if (_connMode == 'usb')
                    const Padding(
                      padding: EdgeInsets.only(bottom: 16.0),
                      child: Text(
                        '💡 USB Modu için telefonunuzda USB Hata Ayıklama açık olmalı ve PC\'de ADB reverse komutu çalıştırılmalıdır.',
                        style: TextStyle(fontSize: 12, color: Colors.grey),
                        textAlign: TextAlign.center,
                      ),
                    ),

                  if (_connMode == 'bluetooth') ...[
                    if (_isBtLoading)
                      const Center(
                        child: Padding(
                          padding: EdgeInsets.all(16.0),
                          child: CircularProgressIndicator(),
                        ),
                      )
                    else if (_pairedDevices.isEmpty) ...[
                      const Text(
                        '⚠️ Eşleşmiş cihaz bulunamadı. Lütfen PC\'nizi telefonun Bluetooth ayarlarından eşleştirin.',
                        style: TextStyle(fontSize: 13, color: Colors.grey),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 12),
                      ElevatedButton.icon(
                        onPressed: _loadBluetoothDevices,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Yenile'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.grey[800],
                          foregroundColor: Colors.white,
                        ),
                      ),
                      const SizedBox(height: 16),
                    ] else ...[
                      DropdownButtonFormField<String>(
                        value: _selectedDeviceAddress,
                        decoration: const InputDecoration(
                          labelText: 'Eşleşmiş PC / Bluetooth Cihazı',
                          border: OutlineInputBorder(),
                        ),
                        items: _pairedDevices.map<DropdownMenuItem<String>>((BluetoothDevice device) {
                          return DropdownMenuItem<String>(
                            value: device.address,
                            child: Text(
                              '${device.name ?? "Bilinmeyen Cihaz"} (${device.address})',
                              overflow: TextOverflow.ellipsis,
                            ),
                          );
                        }).toList(),
                        onChanged: (val) {
                          setState(() {
                            _selectedDeviceAddress = val;
                          });
                        },
                      ),
                      const SizedBox(height: 24),
                    ],
                  ],

                  ElevatedButton(
                    onPressed: _isConnecting ? null : _connect,
                    style: ElevatedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      backgroundColor: Colors.amber,
                      foregroundColor: Colors.black,
                    ),
                    child: _isConnecting
                        ? const CircularProgressIndicator(color: Colors.black)
                        : const Text(
                            'Bağlan',
                            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                          ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class PedalAssignmentScreen extends StatefulWidget {
  final WebSocketChannel? channel;
  final BluetoothConnection? btConnection;
  final String wsUrl;

  const PedalAssignmentScreen({
    Key? key,
    this.channel,
    this.btConnection,
    required this.wsUrl,
  }) : super(key: key);

  @override
  State<PedalAssignmentScreen> createState() => _PedalAssignmentScreenState();
}

class _PedalAssignmentScreenState extends State<PedalAssignmentScreen> {
  final String _phoneId = 'phone_${Random().nextInt(1000000)}';

  void _assignPedal(String pedalType) {
    final payload = {
      'action': 'assign',
      'pedal_type': pedalType,
      'phone_id': _phoneId,
    };
    
    if (widget.channel != null) {
      widget.channel!.sink.add(jsonEncode(payload));
    } else if (widget.btConnection != null) {
      widget.btConnection!.writeString(jsonEncode(payload) + "\n");
    }

    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ActivePedalScreen(
          channel: widget.channel,
          btConnection: widget.btConnection,
          phoneId: _phoneId,
          pedalType: pedalType,
        ),
      ),
    );
  }

  @override
  void dispose() {
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pedal Seçimi'),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Bu telefonu hangi pedal olarak kullanmak istiyorsunuz?',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w500),
            ),
            const SizedBox(height: 48),
            
            ElevatedButton(
              onPressed: () => _assignPedal('gas'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 24),
                backgroundColor: Colors.green[700],
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text(
                '🟢 GAZ PEDALI',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white),
              ),
            ),
            const SizedBox(height: 24),
            
            ElevatedButton(
              onPressed: () => _assignPedal('brake'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 24),
                backgroundColor: Colors.red[700],
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              child: const Text(
                '🔴 FREN PEDALI',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ActivePedalScreen extends StatefulWidget {
  final WebSocketChannel? channel;
  final BluetoothConnection? btConnection;
  final String phoneId;
  final String pedalType;

  const ActivePedalScreen({
    Key? key,
    this.channel,
    this.btConnection,
    required this.phoneId,
    required this.pedalType,
  }) : super(key: key);

  @override
  State<ActivePedalScreen> createState() => _ActivePedalScreenState();
}

class _ActivePedalScreenState extends State<ActivePedalScreen> {
  StreamSubscription? _accelerometerSub;
  double _currentAngle = 0.0;
  double? _baseAngle;
  Timer? _sendTimer;
  bool _isBlackScreen = false;

  @override
  void initState() {
    super.initState();
    _startSensor();
    _startBackgroundService();
    
    // Keep screen awake using wakelock
    WakelockPlus.enable();
    
    // Send data to server periodically (every 20ms = 50Hz)
    _sendTimer = Timer.periodic(const Duration(milliseconds: 20), (timer) {
      _sendData();
    });
  }

  Future<void> _startBackgroundService() async {
    try {
      final androidConfig = FlutterBackgroundAndroidConfig(
        notificationTitle: "ProjectWheel Gyro Pedal",
        notificationText: "Pedal aktif, arka planda veri iletiliyor.",
        notificationImportance: AndroidNotificationImportance.normal,
        notificationIcon: AndroidResource(name: 'ic_launcher', defType: 'mipmap'),
      );
      
      bool success = await FlutterBackground.initialize(androidConfig: androidConfig);
      if (success) {
        await FlutterBackground.enableBackgroundExecution();
      }
    } catch (e) {
      print("Background service init error: $e");
    }
  }

  void _startSensor() {
    _accelerometerSub = accelerometerEvents.listen((AccelerometerEvent event) {
      // Calculate tilt angle using Y and Z axes (assuming phone is tilted along its length)
      // pitch = atan2(y, z) * 180 / pi
      double angle = atan2(event.y, event.z) * 180 / pi;
      
      setState(() {
        _currentAngle = angle;
        if (_baseAngle == null) {
          _baseAngle = angle;
        }
      });
    });
  }

  void _calibrate() {
    setState(() {
      _baseAngle = _currentAngle;
    });
  }

  void _sendData() {
    if (_baseAngle == null) return;
    
    // Angle relative to calibrated base
    double relativeAngle = _currentAngle - _baseAngle!;

    final payload = {
      'phone_id': widget.phoneId,
      'pedal_type': widget.pedalType,
      'angle': relativeAngle,
    };
    
    final dataStr = jsonEncode(payload);
    
    try {
      if (widget.channel != null) {
        widget.channel!.sink.add(dataStr);
      } else if (widget.btConnection != null) {
        if (!widget.btConnection!.isConnected) {
          throw Exception("Bluetooth connection closed");
        }
        widget.btConnection!.writeString(dataStr + "\n");
      }
    } catch (e) {
      // Handle connection loss
      _sendTimer?.cancel();
      _accelerometerSub?.cancel();
      WakelockPlus.disable();
      if (FlutterBackground.isBackgroundExecutionEnabled) {
        FlutterBackground.disableBackgroundExecution();
      }
      if (widget.btConnection != null) {
        widget.btConnection!.dispose();
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Bağlantı koptu!'),
          backgroundColor: Colors.redAccent,
        ),
      );
      Navigator.popUntil(context, (route) => route.isFirst);
    }
  }

  @override
  void dispose() {
    _sendTimer?.cancel();
    _accelerometerSub?.cancel();
    WakelockPlus.disable();
    if (FlutterBackground.isBackgroundExecutionEnabled) {
      FlutterBackground.disableBackgroundExecution();
    }
    if (widget.btConnection != null) {
      widget.btConnection!.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.pedalType == 'gas' ? '🟢 GAZ PEDALI' : '🔴 FREN PEDALI';
    final activeColor = widget.pedalType == 'gas' ? Colors.green : Colors.red;
    
    double relativeAngle = 0.0;
    if (_baseAngle != null) {
      relativeAngle = _currentAngle - _baseAngle!;
    }
    
    // Visual percentage helper for UI progress bar
    double visualPerc = (relativeAngle.abs() * 2).clamp(0.0, 100.0) / 100.0;

    if (_isBlackScreen) {
      return Scaffold(
        backgroundColor: Colors.black,
        body: GestureDetector(
          onTap: () {
            setState(() {
              _isBlackScreen = false;
            });
          },
          child: Container(
            color: Colors.black,
            width: double.infinity,
            height: double.infinity,
            alignment: Alignment.center,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.power_settings_new, color: Colors.grey, size: 48),
                const SizedBox(height: 16),
                Text(
                  'Ekran Karartıldı (Güç Tasarrufu)\nPedal Aktif',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey[600], fontSize: 16),
                ),
                const SizedBox(height: 32),
                Text(
                  'Ekrana dokunarak çıkabilirsiniz',
                  style: TextStyle(color: Colors.grey[800], fontSize: 12),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        backgroundColor: Colors.transparent,
        elevation: 0,
        automaticallyImplyLeading: false,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.pedalType == 'gas' ? 'GAZ AKTİF' : 'FREN AKTİF',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: activeColor),
            ),
            const SizedBox(height: 24),
            
            Text(
              '${relativeAngle.toStringAsFixed(1)}°',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 72, fontFamily: 'monospace', fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            
            Text(
              'Sıfır Referansı: ${_baseAngle?.toStringAsFixed(1)}°',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 14, color: Colors.grey),
            ),
            const SizedBox(height: 32),
            
            // Visual Level Bar
            Container(
              height: 32,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.grey[700]!),
                borderRadius: BorderRadius.circular(16),
                color: Colors.grey[900],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(16),
                child: FractionallySizedBox(
                  alignment: Alignment.centerLeft,
                  widthFactor: visualPerc,
                  child: Container(
                    color: activeColor,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 48),

            ElevatedButton.icon(
              onPressed: () {
                setState(() {
                  _isBlackScreen = true;
                });
              },
              icon: const Icon(Icons.power_off),
              label: const Text('EKRANI KARART (GÜÇ TASARRUFU)'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 18),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                backgroundColor: Colors.amber[900],
                foregroundColor: Colors.white,
              ),
            ),
            const SizedBox(height: 16),
            
            ElevatedButton.icon(
              onPressed: _calibrate,
              icon: const Icon(Icons.compass_calibration),
              label: const Text('SIFIR NOKTASINI AYARLA'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 18),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                backgroundColor: Colors.grey[800],
                foregroundColor: Colors.white,
              ),
            ),
            const SizedBox(height: 24),
            
            TextButton(
              onPressed: () {
                Navigator.pop(context);
              },
              child: const Text('Pedal Atamasını Değiştir', style: TextStyle(color: Colors.grey)),
            ),
          ],
        ),
      ),
    );
  }
}
