export interface IDrone extends mongoose.Document {
  deviceSerialNumber: string;
  deviceName: string;
  deviceCategory: string;
  metadata: {
    alias: string;
    description: string;
  };
  isUsingAiDetection: boolean;
  streamIsOn: boolean;
  streamUrl: string;
  webRTCUrl: string,
  streamCredentials?: {
    userName: string;
    password: string;
    port: string;
  };
  cameras?: string[];
  incidents: Array<{
    imageUrl: string;
    coordinates: {
      type: string;
      coordinates: number[];
    };
    objectBBox: number[];
    createdAt: Date;
  }>;
}
