import { useEffect, useState } from 'react';
import { View, ActivityIndicator, Text } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as Updates from 'expo-updates';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import HomeScreen from './src/screens/HomeScreen';
import VoiceScreen from './src/screens/VoiceScreen';
import LoginScreen from './src/screens/LoginScreen';
import AboutScreen from './src/screens/AboutScreen';
import CallHistoryScreen from './src/screens/CallHistoryScreen';
import KnowledgeBaseScreen from './src/screens/KnowledgeBaseScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import { getToken } from './src/auth';

const Stack = createNativeStackNavigator();

export default function App() {
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [authed, setAuthed] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<'checking' | 'updating' | 'done'>(__DEV__ ? 'done' : 'checking');

  useEffect(() => {
    if (__DEV__) return;
    (async () => {
      try {
        const result = await Updates.checkForUpdateAsync();
        if (result.isAvailable) {
          setUpdateStatus('updating');
          await Updates.fetchUpdateAsync();
          await Updates.reloadAsync();
          return; // app restarts here, nothing after this line runs
        }
      } catch {
        // offline or update check failed -- just continue with what's installed
      }
      setUpdateStatus('done');
    })();
  }, []);

  useEffect(() => {
    if (updateStatus !== 'done') return;
    getToken().then(t => setAuthed(!!t)).finally(() => setCheckingAuth(false));
  }, [updateStatus]);

  if (updateStatus !== 'done' || checkingAuth) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff' }}>
        <ActivityIndicator color="#2f5bff" />
        {updateStatus === 'updating' && <Text style={{ marginTop: 12, color: '#5b6478', fontSize: 13 }}>Updating…</Text>}
      </View>
    );
  }

  return (
    <NavigationContainer>
      {authed ? (
        <Stack.Navigator screenOptions={{ headerShown: false }}>
          <Stack.Screen name="Home">
            {(props) => <HomeScreen {...props} onSignOut={() => setAuthed(false)} />}
          </Stack.Screen>
          <Stack.Screen name="Voice" component={VoiceScreen} />
          <Stack.Screen name="About" component={AboutScreen} />
          <Stack.Screen name="CallHistory" component={CallHistoryScreen} />
          <Stack.Screen name="KnowledgeBase" component={KnowledgeBaseScreen} />
          <Stack.Screen name="Dashboard" component={DashboardScreen} />
        </Stack.Navigator>
      ) : (
        <LoginScreen onAuthenticated={() => setAuthed(true)} />
      )}
      <StatusBar style="dark" />
    </NavigationContainer>
  );
}
