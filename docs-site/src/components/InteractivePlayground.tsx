import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useSelector, useDispatch } from 'react-redux';
import { RootState, nextStep, setUserInput } from '../store';
import { Rocket, CheckCircle2, AlertCircle } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

const schema = z.object({
  apiEndpoint: z.string().url("Must be a valid HTTPS URL").includes("https://", { message: "Must use HTTPS" }),
  rateLimit: z.number().min(10, "Must be at least 10").max(1000, "Cannot exceed 1000"),
});

type FormData = z.infer<typeof schema>;

function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

export default function InteractivePlayground() {
  const dispatch = useDispatch();
  const step = useSelector((state: RootState) => state.playground.tutorialStep);
  const savedInput = useSelector((state: RootState) => state.playground.userInput);

  const { register, handleSubmit, formState: { errors, isSubmitSuccessful } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { apiEndpoint: savedInput || '', rateLimit: 100 }
  });

  const onSubmit = (data: FormData) => {
    dispatch(setUserInput(data.apiEndpoint));
    dispatch(nextStep());
  };

  return (
    <div className="p-6 my-8 rounded-2xl border border-white/40 shadow-xl bg-white/60 backdrop-blur-xl">
      <div className="flex items-center space-x-3 mb-6">
        <div className="p-2 bg-blue-500/10 rounded-lg">
          <Rocket className="text-blue-600 w-6 h-6" />
        </div>
        <div>
          <h3 className="text-xl font-semibold m-0 text-gray-900">Interactive API Setup (Step {step})</h3>
          <p className="text-sm text-gray-500 m-0">Powered by Redux, Zod, and Tailwind v4</p>
        </div>
      </div>

      {isSubmitSuccessful && step > 1 ? (
        <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-center space-x-3">
          <CheckCircle2 className="text-emerald-600 w-5 h-5" />
          <p className="m-0 text-emerald-800 font-medium">Successfully configured! Redux saved: {savedInput}</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Webhook Target URL</label>
            <input 
              {...register('apiEndpoint')}
              placeholder="https://api.example.com/webhook"
              className={cn(
                "w-full px-4 py-2 rounded-xl border bg-white/50 focus:ring-2 focus:outline-none transition-all",
                errors.apiEndpoint ? "border-red-400 focus:ring-red-200" : "border-gray-200 focus:border-blue-400 focus:ring-blue-100"
              )}
            />
            {errors.apiEndpoint && (
              <p className="text-red-500 text-sm mt-1 flex items-center">
                <AlertCircle className="w-4 h-4 mr-1" />
                {errors.apiEndpoint.message}
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Rate Limit (requests/sec)</label>
            <input 
              type="number"
              {...register('rateLimit', { valueAsNumber: true })}
              className={cn(
                "w-full px-4 py-2 rounded-xl border bg-white/50 focus:ring-2 focus:outline-none transition-all",
                errors.rateLimit ? "border-red-400 focus:ring-red-200" : "border-gray-200 focus:border-blue-400 focus:ring-blue-100"
              )}
            />
            {errors.rateLimit && (
              <p className="text-red-500 text-sm mt-1 flex items-center">
                <AlertCircle className="w-4 h-4 mr-1" />
                {errors.rateLimit.message}
              </p>
            )}
          </div>

          <button 
            type="submit"
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl transition-colors shadow-sm"
          >
            Save Configuration
          </button>
        </form>
      )}
    </div>
  );
}
